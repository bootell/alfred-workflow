#!/usr/bin/env python3
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def deep_parse(raw_text, max_depth=20):
    if raw_text is None or raw_text.strip() == "":
        return {"error": "empty input"}, 0

    value = raw_text
    depth = 0

    for _ in range(max_depth):
        if not isinstance(value, str):
            break

        parsed, next_value = parse_once(value)
        if not parsed:
            break

        value = next_value
        depth += 1

    return value, depth


def parse_once(text):
    try:
        return True, json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    try:
        return True, ast.literal_eval(text)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return False, text


def write_temp_json(value, directory=None):
    target_dir = Path(directory) if directory is not None else None
    if target_dir is not None:
        target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="alfred-json-",
        suffix=".json",
        dir=target_dir,
        delete=False,
    ) as output:
        json.dump(value, output, ensure_ascii=False, indent=2, default=str)
        output.write("\n")
        return Path(output.name)


def read_clipboard():
    completed = subprocess.run(
        ["pbpaste"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def output_directory():
    alfred_cache = os.environ.get("alfred_workflow_cache")
    if alfred_cache:
        return Path(alfred_cache)
    return None


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    raw_text = args[0] if args and args[0] else read_clipboard()
    value, _depth = deep_parse(raw_text)
    output_path = write_temp_json(value, directory=output_directory())
    sys.stdout.write(output_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
