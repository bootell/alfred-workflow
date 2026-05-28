# IP Lookup

Keyword: `ip`

Look up IP geolocation for IP addresses, domains, or the current public IP.

## Usage

- `ip`: query the current public IP address and geolocation.
- `ip 8.8.8.8`: query an IPv4 address.
- `ip 2001:4860:4860::8888`: query an IPv6 address.
- `ip example.com`: resolve the domain, query the first resolved IP address, and show its geolocation.

Press Return on an item to copy that item's title.

## Output

- First item: `country regionName city district`
- Network items: `isp`, then `org`
- Optional `IP Flags` item: `mobile`, `proxy`, or `mobile / proxy`, shown only when one of those flags applies

When the query is empty, the first item shows the current public IP address. The following items then show location (`country regionName city district`), network (`isp`, then `org`), and optional connection or IP range flags.

For private or reserved IP ranges, the workflow only shows a single `private` or `reserved` item with the `IP Flags` subtitle.

## Configuration

- `KEYWORD`: Alfred keyword. Default: `ip`
- `LANGUAGE`: ip-api response language. Default: `zh-CN`
- `TIMEOUT_SECONDS`: network timeout in seconds. Default: `5`

`LANGUAGE` is passed to ip-api as the `lang` parameter. Common values include `zh-CN`, `en`, `ja`, `de`, `es`, and `fr`.

## Service

This workflow uses the free ip-api.com JSON endpoint. The free endpoint does not require an API key, uses HTTP, is rate limited, and is intended for non-commercial use.
