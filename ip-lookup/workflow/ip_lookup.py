#!/usr/bin/env python3
import ipaddress
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_KEYWORD = "ip"
DEFAULT_LANGUAGE = "zh-CN"
DEFAULT_TIMEOUT_SECONDS = 5.0
API_BASE_URL = "http://ip-api.com/json"
API_FIELDS = (
    "status",
    "message",
    "query",
    "country",
    "regionName",
    "city",
    "district",
    "isp",
    "org",
    "mobile",
    "proxy",
)


class LookupError(Exception):
    pass


class Config:
    def __init__(self, keyword, language, timeout_seconds):
        self.keyword = keyword
        self.language = language
        self.timeout_seconds = timeout_seconds


def load_config(env):
    return Config(
        keyword=env.get("KEYWORD", DEFAULT_KEYWORD).strip() or DEFAULT_KEYWORD,
        language=env.get("LANGUAGE", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE,
        timeout_seconds=parse_timeout(env.get("TIMEOUT_SECONDS")),
    )


def parse_timeout(value):
    if value is None or str(value).strip() == "":
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_TIMEOUT_SECONDS


def normalize_ip(text):
    return str(ipaddress.ip_address(text.strip()))


def resolve_domain(hostname):
    addresses = []
    for result in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM):
        address = result[4][0]
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise OSError(f"No IP addresses found for {hostname}")
    return addresses


def resolve_target(query, resolver=resolve_domain):
    raw_query = (query or "").strip()
    if not raw_query:
        return "Current IP", None

    try:
        ip_address = normalize_ip(raw_query)
        return ip_address, ip_address
    except ValueError:
        pass

    addresses = resolver(raw_query)
    return raw_query, addresses[0]


def build_url(target, config):
    query = urllib.parse.urlencode(
        {
            "fields": ",".join(API_FIELDS),
            "lang": config.language,
        }
    )
    if target is None:
        return f"{API_BASE_URL}/?{query}"
    encoded_target = urllib.parse.quote(target, safe="")
    return f"{API_BASE_URL}/{encoded_target}?{query}"


def fetch_ip_info(target, config):
    request = urllib.request.Request(
        build_url(target, config),
        headers={"User-Agent": "alfred-ip-lookup/1.0"},
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=config.timeout_seconds,
        ) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read().decode(charset)
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        raise LookupError(str(error))

    try:
        return json.loads(payload)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as error:
        raise LookupError(f"Invalid response: {error}")


def location_label(payload):
    parts = [
        payload.get("country"),
        payload.get("regionName"),
        payload.get("city"),
        payload.get("district"),
    ]
    return " ".join(str(part) for part in parts if part)


def target_subtitle(display_target, payload):
    ip_address = payload.get("query") or display_target
    if display_target == "Current IP":
        return "Current public IP"
    if display_target != ip_address:
        return f"{display_target} -> {ip_address}"
    return ip_address


def summary_title(display_target, payload):
    if display_target == "Current IP":
        return payload.get("query") or "Current IP"
    return location_label(payload) or payload.get("query") or display_target


def build_items(query, config, fetcher=fetch_ip_info, resolver=resolve_domain):
    try:
        display_target, lookup_target = resolve_target(query, resolver=resolver)
    except OSError as error:
        return error_item("Unable to resolve domain", f"{query}: {error}")

    try:
        payload = fetcher(lookup_target, config)
    except LookupError as error:
        return error_item("IP lookup failed", str(error))

    if payload.get("status") != "success":
        range_flag = ip_range_flag(payload)
        if range_flag:
            return ip_range_items(display_target, lookup_target, payload, range_flag)
        return error_item("IP lookup failed", payload.get("message") or "Unknown error")

    if display_target == "Current IP":
        items = [
            alfred_item(payload.get("query") or "Current IP", "Current public IP"),
            alfred_item(location_label(payload) or payload.get("query") or "", "Location"),
        ]
        items.extend(network_items(payload))
        connection = connection_title(payload)
        if connection:
            items.append(alfred_item(connection, "IP Flags"))
        return items

    items = [
        alfred_item(summary_title(display_target, payload), target_subtitle(display_target, payload)),
    ]
    items.extend(network_items(payload))
    connection = connection_title(payload)
    if connection:
        items.append(alfred_item(connection, "IP Flags"))
    return items


def network_items(payload):
    items = []
    if payload.get("isp"):
        items.append(alfred_item(str(payload["isp"]), "ISP"))
    if payload.get("org"):
        items.append(alfred_item(str(payload["org"]), "Org"))
    if not items:
        items.append(alfred_item(payload.get("query") or "", "Network"))
    return items


def ip_range_flag(payload):
    message = (payload.get("message") or "").lower()
    if message == "private range":
        return "private"
    if message == "reserved range":
        return "reserved"
    return None


def ip_range_items(display_target, lookup_target, payload, range_flag):
    return [
        alfred_item(range_flag, "IP Flags"),
    ]


def connection_title(payload):
    return " / ".join(
        part
        for part in [
            true_bool_field("mobile", payload.get("mobile")),
            true_bool_field("proxy", payload.get("proxy")),
        ]
        if part
    )


def true_bool_field(label, value):
    if value is True:
        return label
    return None


def alfred_item(title, subtitle, valid=True):
    item = {
        "title": title,
        "subtitle": subtitle,
        "arg": title,
        "valid": valid,
        "text": {
            "copy": title,
            "largetype": title,
        },
    }
    if valid:
        item["match"] = f"{title} {subtitle}"
    return item


def error_item(title, subtitle):
    return [
        {
            "title": title,
            "subtitle": subtitle,
            "valid": False,
        }
    ]


def run(argv=None, env=None, fetcher=fetch_ip_info, resolver=resolve_domain):
    args = sys.argv[1:] if argv is None else argv
    query = args[0] if args else ""
    config = load_config(os.environ if env is None else env)
    return json.dumps(
        {
            "items": build_items(
                query,
                config,
                fetcher=fetcher,
                resolver=resolver,
            )
        },
        ensure_ascii=False,
    )


def main(argv=None):
    sys.stdout.write(run(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
