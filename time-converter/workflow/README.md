# Time Converter

Keyword: `time`

Use this Alfred workflow to convert Unix timestamps and time strings across configurable time zones.
Time-zone result subtitles include a country flag, the time zone name, and its UTC offset, for example `🇨🇳 Asia/Shanghai (UTC+08:00)`. Flags come from the system time-zone country table (`zone.tab`); unmapped zones use `🌐`.

## Usage

- `time`: show the current Unix timestamp in seconds, then the current time for each output time zone.
- `time 1700000000`: convert a seconds timestamp to each output time zone.
- `time 1700000000000`: convert a milliseconds timestamp to each output time zone.
- `time 2023-11-15 06:13:20`: parse the time in `INPUT_TZ`, show the seconds timestamp first, then each output time zone.

Press Return on an item to copy that item's title.

## Configuration

- `KEYWORD`: Alfred keyword. Default: `time`
- `INPUT_TZ`: time zone used to parse time strings. Default: `Asia/Shanghai`
- `OUTPUT_TZS`: comma-separated output time zones. Default: `Asia/Shanghai`
- `TIME_FORMAT`: display format. Default: `YYYY-MM-DD HH:mm:ss`

`TIME_FORMAT` also accepts Python `strftime` formats such as `%Y-%m-%d %H:%M:%S`.
