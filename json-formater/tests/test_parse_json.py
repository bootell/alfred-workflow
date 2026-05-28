import importlib.util
import io
import json
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock
from urllib.parse import unquote, urlparse


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "workflow" / "parse_json.py"


def load_module():
    spec = importlib.util.spec_from_file_location("parse_json", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeepJsonParseTests(unittest.TestCase):
    def test_parses_plain_json_object(self):
        parser = load_module()

        value, depth = parser.deep_parse('{"a": 1, "b": true}')

        self.assertEqual(value, {"a": 1, "b": True})
        self.assertEqual(depth, 1)

    def test_keeps_parsing_json_strings_until_value_is_not_string(self):
        parser = load_module()

        value, depth = parser.deep_parse('"\\"{\\\\\\"a\\\\\\":1}\\""')

        self.assertEqual(value, {"a": 1})
        self.assertEqual(depth, 3)

    def test_falls_back_to_python_literal_deserialization(self):
        parser = load_module()

        value, depth = parser.deep_parse("{'a': 1, 'b': True}")

        self.assertEqual(value, {"a": 1, "b": True})
        self.assertEqual(depth, 1)

    def test_returns_original_text_when_nothing_can_parse(self):
        parser = load_module()

        value, depth = parser.deep_parse("plain text")

        self.assertEqual(value, "plain text")
        self.assertEqual(depth, 0)

    def test_empty_input_returns_error_object(self):
        parser = load_module()

        value, depth = parser.deep_parse("   ")

        self.assertEqual(value, {"error": "empty input"})
        self.assertEqual(depth, 0)

    def test_writes_final_value_as_formatted_json_file(self):
        parser = load_module()

        with tempfile.TemporaryDirectory() as directory:
            output_path = parser.write_temp_json({"message": "你好"}, directory=directory)

            self.assertEqual(output_path.suffix, ".json")
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                '{\n  "message": "你好"\n}\n',
            )

    def test_writes_python_only_literal_values_as_json_strings(self):
        parser = load_module()

        with tempfile.TemporaryDirectory() as directory:
            output_path = parser.write_temp_json({"data": b"abc"}, directory=directory)

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                '{\n  "data": "b\\u0027abc\\u0027"\n}\n'.replace("\\u0027", "'"),
            )

    def test_main_prints_json_file_url_for_alfred_open_url(self):
        parser = load_module()

        with tempfile.TemporaryDirectory() as directory:
            stdout = io.StringIO()
            original_write_temp_json = parser.write_temp_json

            def write_in_test_directory(value, directory=None):
                self.assertIsNone(directory)
                return original_write_temp_json(value, directory=directory)

            with (
                mock.patch.object(
                    parser,
                    "write_temp_json",
                    side_effect=write_in_test_directory,
                ),
                mock.patch.object(
                    parser.subprocess,
                    "run",
                    side_effect=AssertionError("main should not open files"),
                ) as subprocess_run,
                redirect_stdout(stdout),
            ):
                result = parser.main(['{"a": 1}'])

            self.assertEqual(result, 0)
            subprocess_run.assert_not_called()

            output = stdout.getvalue()
            self.assertFalse(output.endswith("\n"))

            parsed_output = urlparse(output)
            self.assertEqual(parsed_output.scheme, "file")

            output_path = pathlib.Path(unquote(parsed_output.path))
            self.assertEqual(output_path.suffix, ".json")
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                {"a": 1},
            )

    def test_main_writes_json_to_alfred_workflow_cache_when_available(self):
        parser = load_module()

        with tempfile.TemporaryDirectory() as directory:
            cache_directory = pathlib.Path(directory) / "alfred-cache"
            stdout = io.StringIO()

            with (
                mock.patch.dict(
                    os.environ,
                    {"alfred_workflow_cache": str(cache_directory)},
                ),
                mock.patch.object(
                    parser.subprocess,
                    "run",
                    side_effect=AssertionError("main should not open files"),
                ),
                redirect_stdout(stdout),
            ):
                result = parser.main(['{"cached": true}'])

            self.assertEqual(result, 0)
            self.assertTrue(cache_directory.is_dir())

            output = stdout.getvalue()
            parsed_output = urlparse(output)
            output_path = pathlib.Path(unquote(parsed_output.path))

            self.assertEqual(output_path.parent.resolve(), cache_directory.resolve())
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                {"cached": True},
            )


if __name__ == "__main__":
    unittest.main()
