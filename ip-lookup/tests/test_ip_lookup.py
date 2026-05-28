import importlib.util
import json
import pathlib
import plistlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "workflow" / "ip_lookup.py"
PLIST_PATH = pathlib.Path(__file__).resolve().parents[1] / "workflow" / "info.plist"


def load_module():
    spec = importlib.util.spec_from_file_location("ip_lookup", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IpLookupTests(unittest.TestCase):
    def test_config_defaults_and_overrides(self):
        ip_lookup = load_module()

        config = ip_lookup.load_config({})
        self.assertEqual(config.keyword, "ip")
        self.assertEqual(config.language, "zh-CN")
        self.assertEqual(config.timeout_seconds, 5.0)

        config = ip_lookup.load_config(
            {
                "KEYWORD": "whereip",
                "LANGUAGE": "en",
                "TIMEOUT_SECONDS": "2.5",
            }
        )
        self.assertEqual(config.keyword, "whereip")
        self.assertEqual(config.language, "en")
        self.assertEqual(config.timeout_seconds, 2.5)

    def test_ip_input_queries_that_ip_with_configured_language(self):
        ip_lookup = load_module()
        calls = []

        def fetcher(target, config):
            calls.append((target, config.language, config.timeout_seconds))
            return {
                "status": "success",
                "query": target,
                "country": "美国",
                "regionName": "加利福尼亚州",
                "city": "Mountain View",
                "district": "Old Farm District",
                "isp": "Google LLC",
                "org": "Google Public DNS",
                "mobile": False,
                "proxy": False,
            }

        items = ip_lookup.build_items(
            "8.8.8.8",
            ip_lookup.Config(keyword="ip", language="zh-CN", timeout_seconds=3.0),
            fetcher=fetcher,
        )

        self.assertEqual(calls, [("8.8.8.8", "zh-CN", 3.0)])
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["title"], "美国 加利福尼亚州 Mountain View Old Farm District")
        self.assertEqual(items[0]["subtitle"], "8.8.8.8")
        self.assertEqual(items[0]["arg"], items[0]["title"])
        self.assertEqual(items[0]["text"]["copy"], items[0]["title"])
        self.assertEqual(items[1]["title"], "Google LLC")
        self.assertEqual(items[1]["subtitle"], "ISP")
        self.assertEqual(items[2]["title"], "Google Public DNS")
        self.assertEqual(items[2]["subtitle"], "Org")

    def test_empty_input_queries_current_public_ip(self):
        ip_lookup = load_module()
        calls = []

        def fetcher(target, config):
            calls.append(target)
            return {
                "status": "success",
                "query": "203.0.113.10",
                "country": "文档国家",
                "regionName": "文档地区",
                "city": "文档城市",
                "district": "文档街区",
                "isp": "Example ISP",
                "org": "Example Org",
                "mobile": True,
                "proxy": False,
            }

        items = ip_lookup.build_items("", ip_lookup.load_config({}), fetcher=fetcher)

        self.assertEqual(calls, [None])
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0]["title"], "203.0.113.10")
        self.assertEqual(items[0]["subtitle"], "Current public IP")
        self.assertEqual(items[1]["title"], "文档国家 文档地区 文档城市 文档街区")
        self.assertEqual(items[1]["subtitle"], "Location")
        self.assertEqual(items[2]["title"], "Example ISP")
        self.assertEqual(items[2]["subtitle"], "ISP")
        self.assertEqual(items[3]["title"], "Example Org")
        self.assertEqual(items[3]["subtitle"], "Org")
        self.assertEqual(items[4]["title"], "mobile")
        self.assertEqual(items[4]["subtitle"], "IP Flags")

    def test_connection_flags_item_only_includes_true_values(self):
        ip_lookup = load_module()

        def fetcher(target, config):
            return {
                "status": "success",
                "query": target,
                "country": "美国",
                "regionName": "加利福尼亚州",
                "city": "Mountain View",
                "district": "",
                "isp": "Google LLC",
                "mobile": False,
                "proxy": True,
            }

        items = ip_lookup.build_items(
            "8.8.8.8",
            ip_lookup.load_config({}),
            fetcher=fetcher,
        )

        self.assertEqual(len(items), 3)
        self.assertEqual(items[2]["title"], "proxy")
        self.assertEqual(items[2]["subtitle"], "IP Flags")

    def test_connection_flags_item_joins_multiple_true_values_with_slash(self):
        ip_lookup = load_module()

        def fetcher(target, config):
            return {
                "status": "success",
                "query": target,
                "country": "美国",
                "regionName": "加利福尼亚州",
                "city": "Mountain View",
                "district": "",
                "isp": "Google LLC",
                "mobile": True,
                "proxy": True,
            }

        items = ip_lookup.build_items(
            "8.8.8.8",
            ip_lookup.load_config({}),
            fetcher=fetcher,
        )

        self.assertEqual(len(items), 3)
        self.assertEqual(items[2]["title"], "mobile / proxy")

    def test_domain_input_resolves_first_ip_then_queries_location(self):
        ip_lookup = load_module()
        calls = []

        def resolver(hostname):
            self.assertEqual(hostname, "example.com")
            return ["2001:db8::1", "93.184.216.34"]

        def fetcher(target, config):
            calls.append(target)
            return {
                "status": "success",
                "query": target,
                "country": "美国",
                "regionName": "",
                "city": "Example City",
                "district": "",
                "isp": "Example ISP",
            }

        items = ip_lookup.build_items(
            "example.com",
            ip_lookup.load_config({}),
            fetcher=fetcher,
            resolver=resolver,
        )

        self.assertEqual(calls, ["2001:db8::1"])
        self.assertEqual(
            items[0]["title"],
            "美国 Example City",
        )
        self.assertEqual(items[0]["subtitle"], "example.com -> 2001:db8::1")

    def test_domain_resolution_failure_returns_invalid_item(self):
        ip_lookup = load_module()

        def resolver(_hostname):
            raise OSError("DNS lookup failed")

        items = ip_lookup.build_items(
            "missing.example",
            ip_lookup.load_config({}),
            resolver=resolver,
        )

        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["valid"])
        self.assertEqual(items[0]["title"], "Unable to resolve domain")
        self.assertIn("missing.example", items[0]["subtitle"])

    def test_private_range_only_shows_range_flag_item(self):
        ip_lookup = load_module()

        def fetcher(target, config):
            return {
                "status": "fail",
                "query": target,
                "message": "private range",
            }

        items = ip_lookup.build_items(
            "192.168.1.1",
            ip_lookup.load_config({}),
            fetcher=fetcher,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "private")
        self.assertEqual(items[0]["subtitle"], "IP Flags")

    def test_reserved_range_only_shows_range_flag_item(self):
        ip_lookup = load_module()

        def fetcher(target, config):
            return {
                "status": "fail",
                "query": target,
                "message": "reserved range",
            }

        items = ip_lookup.build_items(
            "192.0.2.1",
            ip_lookup.load_config({}),
            fetcher=fetcher,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "reserved")
        self.assertEqual(items[0]["subtitle"], "IP Flags")

    def test_other_api_failure_returns_invalid_item(self):
        ip_lookup = load_module()

        def fetcher(target, config):
            return {
                "status": "fail",
                "query": target,
                "message": "invalid query",
            }

        items = ip_lookup.build_items(
            "203.0.113.1",
            ip_lookup.load_config({}),
            fetcher=fetcher,
        )

        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["valid"])
        self.assertEqual(items[0]["title"], "IP lookup failed")
        self.assertEqual(items[0]["subtitle"], "invalid query")

    def test_network_failure_returns_invalid_item(self):
        ip_lookup = load_module()

        def fetcher(target, config):
            raise ip_lookup.LookupError("timed out")

        items = ip_lookup.build_items(
            "8.8.4.4",
            ip_lookup.load_config({}),
            fetcher=fetcher,
        )

        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["valid"])
        self.assertEqual(items[0]["title"], "IP lookup failed")
        self.assertEqual(items[0]["subtitle"], "timed out")

    def test_run_outputs_alfred_json(self):
        ip_lookup = load_module()

        output = ip_lookup.run(
            ["8.8.8.8"],
            env={"LANGUAGE": "en"},
            fetcher=lambda target, config: {
                "status": "success",
                "query": target,
                "country": "United States",
                "regionName": "California",
                "city": "Mountain View",
                "district": "",
            },
        )

        payload = json.loads(output)
        self.assertEqual(
            payload["items"][0]["title"],
            "United States California Mountain View",
        )

    def test_plist_exposes_user_configuration_without_shadowing_variables(self):
        with PLIST_PATH.open("rb") as plist_file:
            plist = plistlib.load(plist_file)

        configured_variables = {
            item["variable"] for item in plist["userconfigurationconfig"]
        }
        workflow_variables = set(plist.get("variables", {}))

        self.assertTrue({"KEYWORD", "LANGUAGE", "TIMEOUT_SECONDS"} <= configured_variables)
        self.assertFalse(configured_variables & workflow_variables)


if __name__ == "__main__":
    unittest.main()
