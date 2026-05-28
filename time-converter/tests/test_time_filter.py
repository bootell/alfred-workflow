import importlib.util
import json
import pathlib
import plistlib
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "workflow" / "time_filter.py"
PLIST_PATH = pathlib.Path(__file__).resolve().parents[1] / "workflow" / "info.plist"


def load_module():
    spec = importlib.util.spec_from_file_location("time_filter", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TimeFilterTests(unittest.TestCase):
    def test_plist_does_not_shadow_user_configuration_with_workflow_variables(self):
        with PLIST_PATH.open("rb") as plist_file:
            plist = plistlib.load(plist_file)

        configured_variables = {
            item["variable"] for item in plist["userconfigurationconfig"]
        }
        workflow_variables = set(plist.get("variables", {}))

        self.assertTrue({"KEYWORD", "INPUT_TZ", "OUTPUT_TZS", "TIME_FORMAT"} <= configured_variables)
        self.assertFalse(configured_variables & workflow_variables)

    def test_config_uses_defaults_and_splits_output_time_zones(self):
        time_filter = load_module()

        config = time_filter.load_config({})

        self.assertEqual(config.input_tz, "Asia/Shanghai")
        self.assertEqual(config.output_tzs, ["Asia/Shanghai"])
        self.assertEqual(config.time_format, "YYYY-MM-DD HH:mm:ss")

        config = time_filter.load_config(
            {
                "INPUT_TZ": "UTC",
                "OUTPUT_TZS": "Asia/Shanghai, UTC, America/Los_Angeles",
                "TIME_FORMAT": "%Y/%m/%d %H:%M",
            }
        )

        self.assertEqual(config.input_tz, "UTC")
        self.assertEqual(
            config.output_tzs,
            ["Asia/Shanghai", "UTC", "America/Los_Angeles"],
        )
        self.assertEqual(config.time_format, "%Y/%m/%d %H:%M")

    def test_no_input_returns_current_seconds_timestamp_then_each_output_timezone(self):
        time_filter = load_module()
        config = time_filter.Config(
            input_tz="Asia/Shanghai",
            output_tzs=["Asia/Shanghai", "UTC"],
            time_format="YYYY-MM-DD HH:mm:ss",
        )
        now = datetime(2023, 11, 15, 6, 13, 20, tzinfo=ZoneInfo("Asia/Shanghai"))

        items = time_filter.build_items("", config, now=now)

        self.assertEqual([item["title"] for item in items], ["1700000000", "2023-11-15 06:13:20", "2023-11-14 22:13:20"])
        self.assertEqual(items[0]["subtitle"], "Unix timestamp (seconds)")
        self.assertEqual(items[1]["subtitle"], "🇨🇳 Asia/Shanghai (UTC+08:00)")
        self.assertEqual(items[2]["subtitle"], "🌐 UTC (UTC+00:00)")
        self.assertEqual(items[0]["arg"], "1700000000")
        self.assertEqual(items[1]["arg"], "2023-11-15 06:13:20")

    def test_seconds_timestamp_input_returns_one_item_per_output_timezone(self):
        time_filter = load_module()
        config = time_filter.Config(
            input_tz="Asia/Shanghai",
            output_tzs=["Asia/Shanghai", "America/Los_Angeles"],
            time_format="YYYY-MM-DD HH:mm:ss",
        )

        items = time_filter.build_items("1700000000", config)

        self.assertEqual([item["title"] for item in items], ["2023-11-15 06:13:20", "2023-11-14 14:13:20"])
        self.assertEqual(
            [item["subtitle"] for item in items],
            [
                "🇨🇳 Asia/Shanghai (UTC+08:00)",
                "🇺🇸 America/Los_Angeles (UTC-08:00)",
            ],
        )
        self.assertEqual([item["arg"] for item in items], ["2023-11-15 06:13:20", "2023-11-14 14:13:20"])

    def test_milliseconds_timestamp_input_is_detected_and_converted(self):
        time_filter = load_module()
        config = time_filter.Config(
            input_tz="Asia/Shanghai",
            output_tzs=["Asia/Shanghai", "UTC"],
            time_format="YYYY-MM-DD HH:mm:ss",
        )

        items = time_filter.build_items("1700000000000", config)

        self.assertEqual([item["title"] for item in items], ["2023-11-15 06:13:20", "2023-11-14 22:13:20"])
        self.assertEqual(
            [item["subtitle"] for item in items],
            ["🇨🇳 Asia/Shanghai (UTC+08:00)", "🌐 UTC (UTC+00:00)"],
        )

    def test_time_input_returns_timestamp_first_then_each_output_timezone(self):
        time_filter = load_module()
        config = time_filter.Config(
            input_tz="Asia/Shanghai",
            output_tzs=["Asia/Shanghai", "UTC"],
            time_format="YYYY-MM-DD HH:mm:ss",
        )

        items = time_filter.build_items("2023-11-15 06:13:20", config)

        self.assertEqual([item["title"] for item in items], ["1700000000", "2023-11-15 06:13:20", "2023-11-14 22:13:20"])
        self.assertEqual(items[0]["subtitle"], "Unix timestamp (seconds)")
        self.assertEqual(items[1]["subtitle"], "🇨🇳 Asia/Shanghai (UTC+08:00)")
        self.assertEqual(items[2]["subtitle"], "🌐 UTC (UTC+00:00)")

    def test_time_input_accepts_configured_display_format_tokens(self):
        time_filter = load_module()
        config = time_filter.Config(
            input_tz="Asia/Shanghai",
            output_tzs=["Asia/Shanghai"],
            time_format="YYYY/MM/DD HH:mm",
        )

        items = time_filter.build_items("2023-11-15 06:13:20", config)

        self.assertEqual(items[1]["title"], "2023/11/15 06:13")

    def test_invalid_input_returns_single_invalid_item(self):
        time_filter = load_module()
        config = time_filter.Config(
            input_tz="Asia/Shanghai",
            output_tzs=["Asia/Shanghai"],
            time_format="YYYY-MM-DD HH:mm:ss",
        )

        items = time_filter.build_items("not a time", config)

        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["valid"])
        self.assertIn("Unable to parse", items[0]["title"])

    def test_main_prints_alfred_json(self):
        time_filter = load_module()

        output = time_filter.run(
            ["1700000000"],
            env={
                "INPUT_TZ": "Asia/Shanghai",
                "OUTPUT_TZS": "UTC",
                "TIME_FORMAT": "YYYY-MM-DD HH:mm:ss",
            },
        )

        payload = json.loads(output)
        self.assertEqual(payload["items"][0]["title"], "2023-11-14 22:13:20")
        self.assertEqual(payload["items"][0]["subtitle"], "🌐 UTC (UTC+00:00)")

    def test_unknown_timezone_flag_falls_back_to_globe(self):
        time_filter = load_module()

        self.assertEqual(time_filter.flag_for_timezone("UTC"), "🌐")
        self.assertEqual(time_filter.flag_for_timezone("Etc/GMT+8"), "🌐")

    def test_default_timezone_country_paths_only_use_zone_tab(self):
        time_filter = load_module()

        self.assertTrue(time_filter.ZONE_TAB_PATHS)
        self.assertTrue(
            all(path.name == "zone.tab" for path in time_filter.ZONE_TAB_PATHS)
        )

    def test_timezone_flags_read_zone_tab_without_hardcoded_fallbacks(self):
        time_filter = load_module()

        with tempfile.TemporaryDirectory() as directory:
            zone_tab = pathlib.Path(directory) / "zone.tab"
            zone_tab.write_text(
                "#country-\n"
                "#code\tcoordinates\tTZ\tcomments\n"
                "CN\t+3114+12128\tAsia/Shanghai\tBeijing Time\n"
                "US\t+340308-1181434\tAmerica/Los_Angeles\tPacific\n",
                encoding="utf-8",
            )

            time_filter.ZONE_TAB_PATHS = (
                zone_tab,
            )
            time_filter.load_zone_country_map.cache_clear()

            self.assertEqual(time_filter.flag_for_timezone("Asia/Shanghai"), "🇨🇳")
            self.assertEqual(
                time_filter.flag_for_timezone("America/Los_Angeles"),
                "🇺🇸",
            )
            self.assertEqual(time_filter.flag_for_timezone("Asia/Tokyo"), "🌐")


if __name__ == "__main__":
    unittest.main()
