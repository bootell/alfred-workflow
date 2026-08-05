#!/usr/bin/python3
import json
import math
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


ACTION_FIELDS = {
    "copy": {"action", "text"},
    "pronounce": {"action", "text", "accent"},
    "open": {"action", "query"},
}
VALID_ACCENTS = {"us", "uk"}
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 60.0


class RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise urllib.error.HTTPError(
            new_url,
            code,
            "Redirects are not allowed",
            headers,
            file_pointer,
        )


def parse_timeout(value):
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    if not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        return DEFAULT_TIMEOUT_SECONDS
    return timeout


def parse_action(raw):
    try:
        action = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("Action must be a JSON object") from error
    if not isinstance(action, dict):
        raise ValueError("Action must be a JSON object")

    name = action.get("action")
    if not isinstance(name, str) or name not in ACTION_FIELDS:
        raise ValueError("Unsupported action")
    if set(action) != ACTION_FIELDS[name]:
        raise ValueError("Unsupported action")
    required_field = "query" if name == "open" else "text"
    value = action.get(required_field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{required_field} must be a non-empty string")
    if name == "pronounce":
        accent = action["accent"]
        if not isinstance(accent, str) or accent not in VALID_ACCENTS:
            raise ValueError("Unsupported accent")
    return action


def copy_text(text, runner=subprocess.run):
    return runner(["/usr/bin/pbcopy"], input=text.encode("utf-8"), check=True)


def build_pronunciation_url(text, accent):
    if accent not in VALID_ACCENTS:
        raise ValueError("Unsupported accent")
    parameters = {"audio": text}
    if accent == "us":
        parameters["type"] = "2"
    elif accent == "uk":
        parameters["type"] = "1"
    return "https://dict.youdao.com/dictvoice?" + urllib.parse.urlencode(parameters)


def notify_failure(runner=subprocess.run):
    return runner(
        [
            "/usr/bin/osascript",
            "-e",
            'display notification "Unable to play pronunciation" with title "Youdao Dictionary"',
        ],
        check=True,
    )


def response_content_type(response):
    headers = response.headers
    if hasattr(headers, "get_content_type"):
        return headers.get_content_type().lower()
    return headers.get("Content-Type", "").split(";", 1)[0].strip().lower()


def production_opener():
    return urllib.request.build_opener(RejectRedirectHandler()).open


def pronounce(
    text,
    accent,
    opener=None,
    runner=subprocess.run,
    notifier=notify_failure,
    timeout=DEFAULT_TIMEOUT_SECONDS,
):
    audio_path = None
    open_request = production_opener() if opener is None else opener
    try:
        with open_request(
            build_pronunciation_url(text, accent),
            timeout=parse_timeout(timeout),
        ) as response:
            if not response_content_type(response).startswith("audio/"):
                raise ValueError("Response content type is not audio")
            audio = response.read()
        if not audio:
            raise ValueError("Response audio is empty")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
            audio_path = audio_file.name
            audio_file.write(audio)
        runner(["/usr/bin/afplay", audio_path], check=True)
        return True
    except Exception as error:
        print(f"Pronunciation failed: {error}", file=sys.stderr)
        try:
            notifier(runner=runner)
        except Exception as notification_error:
            print(f"Pronunciation failure notification failed: {notification_error}", file=sys.stderr)
        return False
    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
            except FileNotFoundError:
                pass


def open_result(query, runner=subprocess.run):
    url = "https://dict.youdao.com/result?" + urllib.parse.urlencode(
        {"word": query, "lang": "en"}
    )
    return runner(["/usr/bin/open", url], check=True)


def dispatch(raw, env=None):
    action = parse_action(raw)
    if action["action"] == "copy":
        copy_text(action["text"])
        return True
    if action["action"] == "pronounce":
        environment = os.environ if env is None else env
        return pronounce(
            action["text"],
            action["accent"],
            timeout=parse_timeout(environment.get("TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        )
    open_result(action["query"])
    return True


def main(argv=None, env=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Expected exactly one action JSON argument", file=sys.stderr)
        return 1
    try:
        return 0 if dispatch(args[0], env=env) else 1
    except ValueError as error:
        print(f"Invalid action: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
