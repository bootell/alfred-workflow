# Alfred Workflows

A small collection of Alfred workflows for everyday developer utilities.

## Workflows

### JSON Formatter

Parse JSON or Python literal text, repeatedly unwrap nested JSON strings, write the final value as a formatted `.json` file, and open it in the browser.

- Keyword: `json`
- Package: `json-formater/json-formater.alfredworkflow`
- Source: `json-formater/workflow/`

Examples:

```text
json {"a":1}
```

```text
json
```

Running `json` without an argument reads the current clipboard.

### Time Converter

Convert Unix timestamps and time strings across configurable time zones.

- Keyword: `time`
- Package: `time-converter/time.alfredworkflow`
- Source: `time-converter/workflow/`

Examples:

```text
time
time 1700000000
time 1700000000000
time 2023-11-15 06:13:20
```

The workflow supports these Alfred user configuration values:

- `KEYWORD`: trigger keyword. Default: `time`
- `INPUT_TZ`: time zone used to parse time strings. Default: `Asia/Shanghai`
- `OUTPUT_TZS`: comma-separated output time zones. Default: `Asia/Shanghai`
- `TIME_FORMAT`: display format. Default: `YYYY-MM-DD HH:mm:ss`

## Installation

1. Download the `.alfredworkflow` file for the workflow you want to use.
2. Open the file with Alfred.
3. Review the workflow configuration in Alfred, then import it.

The packaged workflow files are included in this repository:

- `json-formater/json-formater.alfredworkflow`
- `time-converter/time.alfredworkflow`

## Requirements

- macOS
- Alfred with workflow support
- Python 3 available at `/usr/bin/python3`

The workflows use only Python standard library modules.

## Development

Run the tests from the repository root:

```sh
python3 -m unittest discover -s json-formater/tests
python3 -m unittest discover -s time-converter/tests
```

Project layout:

```text
json-formater/
  workflow/          JSON Formatter source files
  tests/             JSON Formatter tests
  json-formater.alfredworkflow

time-converter/
  workflow/          Time Converter source files
  tests/             Time Converter tests
  time.alfredworkflow
```

## Privacy And Security

These workflows run locally on macOS and do not call external services.

JSON Formatter can read the current clipboard when triggered without an argument. It writes generated `.json` files under Alfred's workflow cache directory (`$alfred_workflow_cache`) when available. Cache cleanup is left to Alfred and macOS.

Time Converter reads only the query text and Alfred workflow configuration values needed for time-zone conversion.

## License

No license has been declared yet. Until a license is added, all rights are reserved by default.
