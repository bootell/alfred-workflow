#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_INPUT_TZ = "Asia/Shanghai"
DEFAULT_OUTPUT_TZS = ["Asia/Shanghai"]
DEFAULT_TIME_FORMAT = "YYYY-MM-DD HH:mm:ss"
GLOBE_FLAG = "🌐"
ZONE_TAB_PATHS = (
    Path("/usr/share/zoneinfo/zone.tab"),
    Path("/var/db/timezone/zoneinfo/zone.tab"),
)
TIMESTAMP_MILLISECONDS_THRESHOLD = 100_000_000_000
NUMERIC_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


class Config:
    def __init__(self, input_tz, output_tzs, time_format):
        self.input_tz = input_tz
        self.output_tzs = output_tzs
        self.time_format = time_format


def load_config(env):
    output_tzs = [
        value.strip()
        for value in env.get("OUTPUT_TZS", ",".join(DEFAULT_OUTPUT_TZS)).split(",")
        if value.strip()
    ]
    if not output_tzs:
        output_tzs = DEFAULT_OUTPUT_TZS[:]

    return Config(
        input_tz=env.get("INPUT_TZ", DEFAULT_INPUT_TZ).strip() or DEFAULT_INPUT_TZ,
        output_tzs=output_tzs,
        time_format=env.get("TIME_FORMAT", DEFAULT_TIME_FORMAT).strip()
        or DEFAULT_TIME_FORMAT,
    )


def resolve_zone(name):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        raise ValueError(f"Unknown time zone: {name}")


def resolve_output_zones(names):
    return [(name, resolve_zone(name)) for name in names]


def is_timestamp(text):
    return bool(NUMERIC_RE.match(text.strip()))


def parse_timestamp(text):
    raw = text.strip()
    value = float(raw)
    kind = "milliseconds" if abs(value) >= TIMESTAMP_MILLISECONDS_THRESHOLD else "seconds"
    seconds = value / 1000 if kind == "milliseconds" else value
    return datetime.fromtimestamp(seconds, tz=timezone.utc), kind


def python_time_format(time_format):
    if "%" in time_format:
        return time_format

    replacements = [
        ("YYYY", "%Y"),
        ("YY", "%y"),
        ("MM", "%m"),
        ("DD", "%d"),
        ("HH", "%H"),
        ("hh", "%I"),
        ("mm", "%M"),
        ("ii", "%M"),
        ("ss", "%S"),
        ("ZZ", "%z"),
    ]

    converted = time_format
    for source, target in replacements:
        converted = converted.replace(source, target)
    return converted


def format_time(value, time_format):
    return value.strftime(python_time_format(time_format))


def parse_time(text, input_tz, display_format):
    raw = normalize_iso_datetime(text.strip())
    zone = resolve_zone(input_tz)

    parsed = parse_with_iso(raw)
    if parsed is None:
        parsed = parse_with_formats(raw, display_format)

    if parsed is None:
        raise ValueError(f"Unable to parse time: {text}")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def normalize_iso_datetime(text):
    if text.endswith("Z"):
        return f"{text[:-1]}+00:00"
    return text


def parse_with_iso(text):
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_with_formats(text, display_format):
    formats = []
    display_python_format = python_time_format(display_format)
    if display_python_format not in formats:
        formats.append(display_python_format)

    formats.extend(
        [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
        ]
    )

    for time_format in formats:
        try:
            return datetime.strptime(text, time_format)
        except ValueError:
            continue
    return None


def timestamp_item(value):
    text = str(int(value.timestamp()))
    return alfred_item(text, "Unix timestamp (seconds)")


def time_item(value, zone_name, zone, time_format):
    zoned_value = value.astimezone(zone)
    text = format_time(zoned_value, time_format)
    return alfred_item(text, timezone_subtitle(zone_name, zoned_value))


def timezone_subtitle(zone_name, value):
    return f"{flag_for_timezone(zone_name)} {zone_name} ({utc_offset_label(value)})"


def flag_for_timezone(zone_name):
    country_code = timezone_country_code(zone_name)
    if not country_code:
        return GLOBE_FLAG
    return country_code_to_flag(country_code)


def timezone_country_code(zone_name):
    return load_zone_country_map().get(zone_name)


@lru_cache(maxsize=1)
def load_zone_country_map():
    zone_tab_path = find_zone_tab_path()
    if zone_tab_path is None:
        return {}

    zone_countries = {}
    with zone_tab_path.open(encoding="utf-8") as zone_file:
        for line in zone_file:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            country_codes = parts[0].split(",")
            zone_name = parts[2]
            zone_countries[zone_name] = country_codes[0]
    return zone_countries


def find_zone_tab_path():
    for path in ZONE_TAB_PATHS:
        if path.exists():
            return path
    return None


def country_code_to_flag(country_code):
    normalized = country_code.upper()
    if len(normalized) != 2 or not normalized.isalpha():
        return GLOBE_FLAG
    regional_indicator_base = 0x1F1E6
    return "".join(
        chr(regional_indicator_base + ord(letter) - ord("A"))
        for letter in normalized
    )


def utc_offset_label(value):
    offset = value.utcoffset()
    if offset is None:
        return "UTC+00:00"

    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_minutes = abs(total_seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


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


def build_items(query, config, now=None):
    try:
        output_zones = resolve_output_zones(config.output_tzs)
    except ValueError as error:
        return error_item(str(error), "Check OUTPUT_TZS in workflow configuration")

    raw_query = (query or "").strip()

    if not raw_query:
        current = now if now is not None else datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=resolve_zone(config.input_tz))

        items = [timestamp_item(current)]
        items.extend(
            time_item(current, zone_name, zone, config.time_format)
            for zone_name, zone in output_zones
        )
        return items

    if is_timestamp(raw_query):
        try:
            value, _kind = parse_timestamp(raw_query)
        except (OverflowError, OSError, ValueError):
            return error_item("Unable to parse timestamp", raw_query)

        return [
            time_item(value, zone_name, zone, config.time_format)
            for zone_name, zone in output_zones
        ]

    try:
        value = parse_time(raw_query, config.input_tz, config.time_format)
    except ValueError as error:
        return error_item(str(error), f"Input time zone: {config.input_tz}")

    items = [timestamp_item(value)]
    items.extend(
        time_item(value, zone_name, zone, config.time_format)
        for zone_name, zone in output_zones
    )
    return items


def run(argv=None, env=None, now=None):
    args = sys.argv[1:] if argv is None else argv
    query = args[0] if args else ""
    config = load_config(os.environ if env is None else env)
    return json.dumps({"items": build_items(query, config, now=now)}, ensure_ascii=False)


def main(argv=None):
    sys.stdout.write(run(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
