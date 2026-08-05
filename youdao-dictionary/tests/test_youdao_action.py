import importlib.util
import io
import json
import pathlib
import unittest
import urllib.error
from contextlib import redirect_stderr
from urllib.parse import parse_qs, urlparse


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "workflow" / "youdao_action.py"


def load_module():
    spec = importlib.util.spec_from_file_location("youdao_action", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YoudaoActionTests(unittest.TestCase):
    def test_action_timeout_accepts_only_bounded_positive_values(self):
        youdao_action = load_module()

        self.assertEqual(youdao_action.parse_timeout("2.75"), 2.75)
        self.assertEqual(youdao_action.parse_timeout("60"), 60.0)
        for value in (
            "nan",
            "inf",
            "+Infinity",
            "-Infinity",
            "0",
            "-1",
            "60.0001",
            "1e308",
            "bad",
            None,
        ):
            with self.subTest(value=value):
                self.assertEqual(youdao_action.parse_timeout(value), 5.0)

    def test_parse_action_accepts_only_the_compact_lookup_action_schemas(self):
        youdao_action = load_module()

        self.assertEqual(
            youdao_action.parse_action('{"action":"copy","text":"释义"}'),
            {"action": "copy", "text": "释义"},
        )
        self.assertEqual(
            youdao_action.parse_action('{"action":"pronounce","text":"hello","accent":"us"}'),
            {"action": "pronounce", "text": "hello", "accent": "us"},
        )
        self.assertEqual(
            youdao_action.parse_action('{"action":"open","query":"hello world"}'),
            {"action": "open", "query": "hello world"},
        )

        for raw in (
            "not json",
            "[]",
            '{"action":"delete","path":"/tmp/x"}',
            '{"action":"copy","text":"   "}',
            '{"action":"pronounce","text":"hello","accent":"au"}',
            '{"action":"pronounce","text":"你好","accent":"default"}',
            '{"action":"pronounce","text":"hello","accent":[]}',
            '{"action":"open","query":"hello","url":"https://evil.example"}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    youdao_action.parse_action(raw)

    def test_copy_text_sends_exact_utf8_bytes_to_fixed_pbcopy_argv(self):
        youdao_action = load_module()
        calls = []

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))

        youdao_action.copy_text("你好; $(open /tmp/nope)", runner=runner)

        self.assertEqual(
            calls,
            [(
                ["/usr/bin/pbcopy"],
                {"input": "你好; $(open /tmp/nope)".encode("utf-8"), "check": True},
            )],
        )

    def test_build_pronunciation_url_uses_fixed_host_encoded_text_and_accent_mapping(self):
        youdao_action = load_module()

        expected_queries = {
            "us": {"audio": ["hello world; &"], "type": ["2"]},
            "uk": {"audio": ["hello world; &"], "type": ["1"]},
        }
        for accent, expected_query in expected_queries.items():
            with self.subTest(accent=accent):
                parsed = urlparse(
                    youdao_action.build_pronunciation_url("hello world; &", accent)
                )
                self.assertEqual(parsed.scheme, "https")
                self.assertEqual(parsed.netloc, "dict.youdao.com")
                self.assertEqual(parsed.path, "/dictvoice")
                self.assertEqual(parse_qs(parsed.query), expected_query)

    def test_pronounce_downloads_audio_plays_it_and_removes_the_temporary_file(self):
        youdao_action = load_module()
        played_paths = []

        class Response:
            headers = {"Content-Type": "audio/mpeg"}

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return b"mp3-bytes"

        def opener(url, timeout):
            self.assertEqual(timeout, 5.0)
            self.assertEqual(
                url,
                "https://dict.youdao.com/dictvoice?audio=hello&type=2",
            )
            return Response()

        def runner(argv, **kwargs):
            self.assertEqual(kwargs, {"check": True})
            self.assertEqual(argv[0], "/usr/bin/afplay")
            path = pathlib.Path(argv[1])
            self.assertEqual(path.suffix, ".mp3")
            self.assertEqual(path.read_bytes(), b"mp3-bytes")
            played_paths.append(path)

        self.assertTrue(youdao_action.pronounce("hello", "us", opener=opener, runner=runner))
        self.assertEqual(len(played_paths), 1)
        self.assertFalse(played_paths[0].exists())

    def test_pronounce_rejects_non_audio_response_and_notifies_without_query_interpolation(self):
        youdao_action = load_module()
        calls = []
        query = 'hello"; do shell script "bad"; --'

        class Response:
            headers = {"Content-Type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return b"not audio"

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertFalse(
                youdao_action.pronounce(
                    query,
                    "uk",
                    opener=lambda _url, timeout: Response(),
                    runner=runner,
                )
            )

        self.assertIn("Pronunciation failed:", stderr.getvalue())
        self.assertEqual(calls[0][0][0], "/usr/bin/osascript")
        self.assertEqual(calls[0][1], {"check": True})
        self.assertNotIn(query, " ".join(calls[0][0]))

    def test_pronounce_rejects_empty_audio_without_starting_the_player(self):
        youdao_action = load_module()
        calls = []

        class Response:
            headers = {"Content-Type": "audio/mpeg"}

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return b""

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertFalse(
                youdao_action.pronounce(
                    "empty",
                    "uk",
                    opener=lambda _url, timeout: Response(),
                    runner=runner,
                )
            )
        self.assertEqual([argv[0] for argv, _kwargs in calls], ["/usr/bin/osascript"])
        self.assertIn("Response audio is empty", stderr.getvalue())

    def test_pronounce_removes_temporary_audio_when_playback_and_notification_fail(self):
        youdao_action = load_module()
        temporary_paths = []

        class Response:
            headers = {"Content-Type": "audio/mpeg"}

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return b"mp3-bytes"

        def runner(argv, **kwargs):
            self.assertEqual(kwargs, {"check": True})
            if argv[0] == "/usr/bin/afplay":
                path = pathlib.Path(argv[1])
                self.assertTrue(path.exists())
                temporary_paths.append(path)
                raise RuntimeError("afplay failed")
            self.assertEqual(argv[0], "/usr/bin/osascript")
            raise RuntimeError("notification failed")

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertFalse(
                youdao_action.pronounce(
                    "hello",
                    "uk",
                    opener=lambda _url, timeout: Response(),
                    runner=runner,
                )
            )

        self.assertEqual(len(temporary_paths), 1)
        self.assertFalse(temporary_paths[0].exists())
        self.assertIn("afplay failed", stderr.getvalue())
        self.assertIn("notification failed", stderr.getvalue())

    def test_open_result_passes_injection_shaped_query_only_as_fixed_youdao_url_data(self):
        youdao_action = load_module()
        calls = []
        query = "hello & open https://evil.example; $(whoami)"

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))

        youdao_action.open_result(query, runner=runner)

        self.assertEqual(calls[0][0][0], "/usr/bin/open")
        self.assertEqual(calls[0][1], {"check": True})
        parsed = urlparse(calls[0][0][1])
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "dict.youdao.com")
        self.assertEqual(parsed.path, "/result")
        self.assertEqual(parse_qs(parsed.query), {"word": [query], "lang": ["en"]})

    def test_dispatch_routes_only_valid_actions_and_rejects_invalid_input_before_side_effects(self):
        youdao_action = load_module()
        calls = []
        youdao_action.copy_text = lambda text: calls.append(("copy", text))
        youdao_action.pronounce = lambda text, accent, timeout: calls.append(
            ("pronounce", text, accent)
        ) or True
        youdao_action.open_result = lambda query: calls.append(("open", query))

        self.assertTrue(youdao_action.dispatch('{"action":"copy","text":"释义"}'))
        self.assertTrue(
            youdao_action.dispatch('{"action":"pronounce","text":"hello","accent":"uk"}')
        )
        self.assertTrue(youdao_action.dispatch('{"action":"open","query":"hello"}'))
        self.assertEqual(
            calls,
            [("copy", "释义"), ("pronounce", "hello", "uk"), ("open", "hello")],
        )

        with self.assertRaises(ValueError):
            youdao_action.dispatch('{"action":"open","query":"hello","command":"open"}')
        self.assertEqual(len(calls), 3)

    def test_dispatch_passes_environment_timeout_to_pronunciation_download(self):
        youdao_action = load_module()
        calls = []
        youdao_action.pronounce = lambda text, accent, timeout: calls.append(
            (text, accent, timeout)
        ) or True

        self.assertTrue(
            youdao_action.dispatch(
                '{"action":"pronounce","text":"hello","accent":"uk"}',
                env={"TIMEOUT_SECONDS": "2.75"},
            )
        )
        self.assertEqual(calls, [("hello", "uk", 2.75)])

    def test_pronounce_revalidates_timeout_and_passes_default_to_opener(self):
        youdao_action = load_module()
        calls = []

        class Response:
            headers = {"Content-Type": "audio/mpeg"}

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return b"mp3-bytes"

        def opener(url, timeout):
            calls.append((url, timeout))
            return Response()

        self.assertTrue(
            youdao_action.pronounce(
                "hello",
                "us",
                opener=opener,
                runner=lambda _argv, **_kwargs: None,
                timeout=float("inf"),
            )
        )
        self.assertEqual(calls[0][1], 5.0)

    def test_pronounce_download_failure_never_creates_audio_or_starts_afplay(self):
        youdao_action = load_module()
        calls = []
        query = "hello; $(open /tmp/nope)"

        def no_temporary_file(*_args, **_kwargs):
            self.fail("download errors must not create an audio file")

        original_named_temporary_file = youdao_action.tempfile.NamedTemporaryFile
        youdao_action.tempfile.NamedTemporaryFile = no_temporary_file

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))

        try:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertFalse(
                    youdao_action.pronounce(
                        query,
                        "us",
                        opener=lambda _url, timeout: (_ for _ in ()).throw(OSError("download failed")),
                        runner=runner,
                    )
                )
        finally:
            youdao_action.tempfile.NamedTemporaryFile = original_named_temporary_file

        self.assertEqual([argv[0] for argv, _kwargs in calls], ["/usr/bin/osascript"])
        self.assertNotIn(query, " ".join(calls[0][0]))
        self.assertIn("download failed", stderr.getvalue())

    def test_pronunciation_production_redirect_handler_rejects_cross_host_and_https_downgrade(self):
        youdao_action = load_module()
        handler = youdao_action.RejectRedirectHandler()
        production_handlers = youdao_action.production_opener().__self__.handlers
        request = youdao_action.urllib.request.Request(
            "https://dict.youdao.com/dictvoice?audio=hello&type=2"
        )

        self.assertTrue(
            any(isinstance(item, youdao_action.RejectRedirectHandler) for item in production_handlers)
        )

        for destination in (
            "https://evil.example/audio.mp3",
            "http://dict.youdao.com/dictvoice?audio=hello&type=2",
        ):
            with self.subTest(destination=destination):
                with self.assertRaises(urllib.error.HTTPError):
                    handler.redirect_request(
                        request,
                        None,
                        302,
                        "Found",
                        {},
                        destination,
                    )

    def test_pronunciation_redirect_failure_notifies_without_creating_or_playing_audio(self):
        youdao_action = load_module()
        calls = []

        def rejecting_opener(_url, timeout):
            self.assertEqual(timeout, 5.0)
            raise urllib.error.HTTPError(
                "https://evil.example/audio.mp3", 302, "Redirects are not allowed", {}, None
            )

        def no_temporary_file(*_args, **_kwargs):
            self.fail("a redirect failure must not create an audio file")

        original_named_temporary_file = youdao_action.tempfile.NamedTemporaryFile
        youdao_action.tempfile.NamedTemporaryFile = no_temporary_file
        try:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertFalse(
                    youdao_action.pronounce(
                        "hello", "us", opener=rejecting_opener, runner=lambda argv, **kwargs: calls.append((argv, kwargs))
                    )
                )
        finally:
            youdao_action.tempfile.NamedTemporaryFile = original_named_temporary_file

        self.assertEqual([argv[0] for argv, _kwargs in calls], ["/usr/bin/osascript"])
        self.assertIn("Redirects are not allowed", stderr.getvalue())

    def test_main_returns_nonzero_for_invalid_action_without_dispatching_it(self):
        youdao_action = load_module()
        calls = []
        youdao_action.dispatch = lambda raw, env=None: calls.append(raw) or True

        self.assertEqual(youdao_action.main(['{"action":"copy","text":"ok"}']), 0)
        self.assertEqual(calls, ['{"action":"copy","text":"ok"}'])

        youdao_action.dispatch = lambda _raw, env=None: (_ for _ in ()).throw(
            ValueError("bad action")
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(youdao_action.main(['not valid']), 1)
        self.assertIn("bad action", stderr.getvalue())

    def test_non_string_action_is_rejected_by_parse_and_main_before_any_side_effect(self):
        youdao_action = load_module()
        side_effects = []
        youdao_action.copy_text = lambda _text: side_effects.append("copy")
        youdao_action.pronounce = lambda _text, _accent: side_effects.append("pronounce")
        youdao_action.open_result = lambda _query: side_effects.append("open")
        raw = '{"action":[],"text":"hello"}'

        with self.assertRaises(ValueError):
            youdao_action.parse_action(raw)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(youdao_action.main([raw]), 1)
        self.assertIn("Invalid action", stderr.getvalue())
        self.assertEqual(side_effects, [])

    def test_action_script_uses_the_required_system_python_shebang(self):
        self.assertEqual(SCRIPT_PATH.read_text(encoding="utf-8").splitlines()[0], "#!/usr/bin/python3")


if __name__ == "__main__":
    unittest.main()
