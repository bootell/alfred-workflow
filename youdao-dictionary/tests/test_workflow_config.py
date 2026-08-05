import pathlib
import plistlib
import struct
import unittest
import zipfile


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPOSITORY_ROOT / "youdao-dictionary" / "workflow"
PLIST_PATH = WORKFLOW_DIR / "info.plist"
PACKAGE_PATH = REPOSITORY_ROOT / "youdao-dictionary" / "youdao-dictionary.alfredworkflow"
PACKAGE_FILES = {
    "README.md",
    "icon.png",
    "icon-pronunciation.png",
    "info.plist",
    "youdao_action.py",
    "youdao_lookup.py",
}


def load_plist():
    with PLIST_PATH.open("rb") as source:
        return plistlib.load(source)


def objects_by_type(workflow, object_type):
    return [item for item in workflow["objects"] if item["type"] == object_type]


class YoudaoWorkflowConfigurationTests(unittest.TestCase):
    def test_workflow_icons_are_256_square_png_files_with_alpha(self):
        for name in ("icon.png", "icon-pronunciation.png"):
            with self.subTest(name=name):
                png = (WORKFLOW_DIR / name).read_bytes()

                self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(png[12:16], b"IHDR")
                width, height, _depth, color_type, _compression, _filter, _interlace = (
                    struct.unpack(">IIBBBBB", png[16:29])
                )
                self.assertEqual((width, height), (256, 256))
                self.assertIn(color_type, (4, 6))

    def test_identity_and_only_user_configuration_defaults_are_stable(self):
        workflow = load_plist()

        self.assertEqual(workflow["bundleid"], "com.bootell.alfred.youdao-dictionary")
        self.assertEqual(workflow["version"], "1.0.0")
        configurations = workflow["userconfigurationconfig"]
        self.assertEqual([item["variable"] for item in configurations], ["KEYWORD", "TIMEOUT_SECONDS"])
        self.assertEqual(
            [item["config"]["default"] for item in configurations], ["yd", "5"]
        )
        self.assertEqual(
            configurations[1]["description"],
            "Timeout for lookup and pronunciation requests, greater than 0 and at most 60 seconds.",
        )
        self.assertNotIn("variables", workflow)

    def test_script_filter_uses_v3_automatic_queue_and_controlled_action_topology(self):
        workflow = load_plist()
        filters = objects_by_type(workflow, "alfred.workflow.input.scriptfilter")
        actions = objects_by_type(workflow, "alfred.workflow.action.script")

        self.assertEqual(len(filters), 1)
        self.assertEqual(len(actions), 1)
        script_filter = filters[0]
        action = actions[0]
        config = script_filter["config"]
        self.assertEqual(script_filter["version"], 3)
        self.assertEqual(config["keyword"], "{var:KEYWORD}")
        self.assertEqual(config["argumenttype"], 1)
        self.assertTrue(config["argumenttreatemptyqueryasnil"])
        self.assertEqual(config["queuedelaymode"], 0)
        self.assertTrue(config["queuedelayimmediatelyinitially"])
        self.assertEqual(config["queuemode"], 1)
        self.assertEqual(config["runningsubtext"], "Looking up Youdao...")
        self.assertEqual(config["script"], '/usr/bin/python3 youdao_lookup.py "$1"')
        self.assertEqual(config["scriptargtype"], 1)
        self.assertEqual(
            action["config"]["script"], '/usr/bin/python3 youdao_action.py "$1"'
        )
        self.assertEqual(action["config"]["scriptargtype"], 1)
        edges = workflow["connections"][script_filter["uid"]]
        self.assertEqual([edge["destinationuid"] for edge in edges], [action["uid"]])
        self.assertEqual(edges[0]["modifiers"], 0)
        self.assertTrue(edges[0]["vitoclose"])
        self.assertEqual(objects_by_type(workflow, "alfred.workflow.output.clipboard"), [])

    def test_unbound_hotkey_shows_alfred_with_selected_text_prefixed_by_keyword(self):
        workflow = load_plist()
        hotkeys = objects_by_type(workflow, "alfred.workflow.trigger.hotkey")

        self.assertEqual(len(hotkeys), 1)
        hotkey = hotkeys[0]
        config = hotkey["config"]
        self.assertEqual(hotkey["version"], 2)
        self.assertEqual(config["action"], 1)
        self.assertEqual(config["argument"], 1)
        self.assertEqual(config["argumenttext"], "{var:KEYWORD} ")
        self.assertEqual(config["hotkey"], 0)
        self.assertEqual(config["keycode"], 0)
        self.assertEqual(config["hotmod"], 0)

    def test_readmes_describe_shortcuts_network_privacy_and_failures(self):
        for path in (REPOSITORY_ROOT / "README.md", WORKFLOW_DIR / "README.md"):
            text = path.read_text(encoding="utf-8")
            for expected in (
                "完整可见标题",
                "Cmd",
                "Option",
                "Shift Quick Look",
                "Hotkey",
                "KEYWORD",
                "TIMEOUT_SECONDS",
                "标准库",
                "https://dict.youdao.com/jsonapi",
                "未公开",
                "SLA",
                "dictvoice",
                "result",
                "不持久化",
                "仅支持中文和英文",
                "失败",
                "网络翻译",
                "ec/ce",
                "`q`",
                "doctype=json",
                "jsonversion=2",
                "client=mobile",
                'dicts={"count":3,"dicts":[["ec"],["ce"],["web_trans"]]}',
                "适配器可替换",
                "显示/动作协议不变",
                "audio=<查询文本>",
                "美式 `type=2`",
                "英式 `type=1`",
                "中文不显示发音行",
                "缺少音标的英文不显示发音行",
                "URL 编码的 `word=<原查询>` 与 `lang`",
                "Quick Look 与无结果 action 固定使用 `lang=en`",
                "文件路径会在网络请求前被拒绝",
                "`0 < TIMEOUT_SECONDS <= 60`",
                "固定 HTTPS `dict.youdao.com`",
                "不接受任意 URL",
                "同时控制查询与发音请求",
                "不支持的语种会在请求前返回不可操作的错误行",
                "拒绝 HTTP 重定向",
            ):
                self.assertIn(expected, text, f"{path} must document {expected}")

    def test_package_contains_only_runtime_files_with_byte_identical_contents(self):
        with zipfile.ZipFile(PACKAGE_PATH) as package:
            self.assertEqual(set(package.namelist()), PACKAGE_FILES)
            self.assertEqual(len(package.namelist()), len(PACKAGE_FILES))
            self.assertTrue(all(not name.endswith("/") for name in package.namelist()))
            for name in PACKAGE_FILES:
                self.assertEqual(package.read(name), (WORKFLOW_DIR / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
