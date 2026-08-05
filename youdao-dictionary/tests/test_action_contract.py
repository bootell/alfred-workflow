import importlib.util
import json
import pathlib
import unittest


WORKFLOW_DIR = pathlib.Path(__file__).resolve().parents[1] / "workflow"


def load_module(name):
    path = WORKFLOW_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YoudaoActionContractTests(unittest.TestCase):
    def test_lookup_generated_base_and_modifier_arguments_are_all_accepted_by_dispatcher(self):
        youdao_lookup = load_module("youdao_lookup")
        youdao_action = load_module("youdao_action")
        config = youdao_lookup.load_config({})

        english_items = youdao_lookup.build_items(
            "hello",
            config,
            fetcher=lambda _query, _config: {
                "simple": {"word": [{
                    "return-phrase": "hello",
                    "ukphone": "həˈləʊ",
                    "usphone": "həˈloʊ",
                }]},
                "ec": {"word": [{"trs": ["你好"]}]},
            },
        )
        chinese_items = youdao_lookup.build_items(
            "你好",
            config,
            fetcher=lambda _query, _config: {
                "ce": {"word": [{"return-phrase": "你好", "trs": ["hello"]}]}
            },
        )
        no_result_items = youdao_lookup.build_items(
            "unknown",
            config,
            fetcher=lambda _query, _config: {},
        )

        raw_arguments = [
            english_items[0]["arg"],
            english_items[1]["arg"],
            english_items[0]["mods"]["cmd"]["arg"],
            english_items[0]["mods"]["alt"]["arg"],
            chinese_items[0]["arg"],
            no_result_items[0]["arg"],
        ]
        parsed_actions = [youdao_action.parse_action(raw) for raw in raw_arguments]

        self.assertEqual(
            [action["action"] for action in parsed_actions],
            ["copy", "copy", "pronounce", "pronounce", "copy", "open"],
        )
        self.assertEqual(parsed_actions, [json.loads(raw) for raw in raw_arguments])


if __name__ == "__main__":
    unittest.main()
