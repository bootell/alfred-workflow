import importlib.util
import json
import pathlib
import unittest
import urllib.error
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "workflow" / "youdao_lookup.py"


def load_module():
    spec = importlib.util.spec_from_file_location("youdao_lookup", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YoudaoLookupTests(unittest.TestCase):
    def test_config_defaults_and_lookup_url_use_the_fixed_youdao_contract(self):
        youdao_lookup = load_module()

        config = youdao_lookup.load_config({})
        parsed = urlparse(youdao_lookup.build_lookup_url("hello world"))

        self.assertEqual(config.keyword, "yd")
        self.assertEqual(config.timeout_seconds, 5.0)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "dict.youdao.com")
        self.assertEqual(parsed.path, "/jsonapi")
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "q": ["hello world"],
                "doctype": ["json"],
                "jsonversion": ["2"],
                "client": ["mobile"],
                "dicts": ['{"count":3,"dicts":[["ec"],["ce"],["web_trans"]]}'],
            },
        )

    def test_lookup_timeout_accepts_only_bounded_positive_values_and_fetch_revalidates_config(self):
        youdao_lookup = load_module()

        self.assertEqual(
            youdao_lookup.load_config({"TIMEOUT_SECONDS": "60"}).timeout_seconds,
            60.0,
        )
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
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    youdao_lookup.load_config({"TIMEOUT_SECONDS": value}).timeout_seconds,
                    5.0,
                )

        calls = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return b"{}"

        youdao_lookup.fetch_payload(
            "hello",
            youdao_lookup.Config(keyword="yd", timeout_seconds=1e308),
            opener=lambda request, timeout: calls.append((request, timeout)) or Response(),
        )

        self.assertEqual(calls[0][1], 5.0)

    def test_parse_english_word_reads_ec_senses_and_simple_word_forms(self):
        youdao_lookup = load_module()
        payload = {
            "simple": {
                "word": [{
                    "return-phrase": "run",
                    "ukphone": "rʌn",
                    "usphone": "rʌn",
                    "wfs": [
                        {"wf": {"name": "过去式", "value": "ran"}},
                        {"wf": {"name": "过去分词", "value": "run"}},
                    ],
                }]
            },
            "ec": {
                "word": [{
                    "trs": [
                        {"pos": "v.", "tr": [{"l": {"i": ["跑；运行"]}}]},
                        {"pos": "n.", "tr": [{"l": {"i": ["跑步"]}}]},
                    ]
                }]
            },
        }

        result = youdao_lookup.parse_dictionary_result(" run ", payload)

        self.assertEqual(result.query, "run")
        self.assertEqual(result.headword, "run")
        self.assertEqual(result.language, "en")
        self.assertEqual(result.uk_phonetic, "rʌn")
        self.assertEqual(result.us_phonetic, "rʌn")
        self.assertEqual(
            result.senses,
            (
                youdao_lookup.Sense("v.", "跑；运行"),
                youdao_lookup.Sense("n.", "跑步"),
            ),
        )
        self.assertEqual(
            result.forms,
            (
                youdao_lookup.WordForm("过去式", "ran"),
                youdao_lookup.WordForm("过去分词", "run"),
            ),
        )

    def test_parse_english_phrase_keeps_definition_without_a_part_of_speech(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "look after",
            {
                "simple": {"word": [{"return-phrase": "look after"}]},
                "ec": {"word": [{"trs": [{"tr": [{"l": {"i": ["照顾"]}}]}]}]},
            },
        )

        self.assertEqual(result.senses, (youdao_lookup.Sense("", "照顾"),))

    def test_parse_splits_leading_pos_from_ec_definition_and_reads_forms_from_simple_and_ec(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "test",
            {
                "simple": {"word": [{
                    "return-phrase": "test",
                    "wfs": [{"wf": {"name": "复数", "value": "tests"}}],
                }]},
                "ec": {"word": [{
                    "trs": [{"tr": [{"l": {"i": ["v. 测试；检验"]}}]}],
                    "wfs": [{"wf": {"name": "过去式", "value": "tested"}}],
                }]},
            },
        )

        self.assertEqual(result.senses, (youdao_lookup.Sense("v.", "测试；检验"),))
        self.assertEqual(
            result.forms,
            (youdao_lookup.WordForm("复数", "tests"), youdao_lookup.WordForm("过去式", "tested")),
        )

    def test_parse_chinese_mixed_nodes_prefers_text_nodes_and_omits_phonetics(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "你好",
            {
                "ce": {
                    "word": [{
                        "return-phrase": "你好",
                        "trs": [{
                            "tr": [{"l": {"i": [{"#text": "你好", "@type": "meta"}, {"@type": "structural"}, "您好"]}}]
                        }],
                    }]
                }
            },
        )

        self.assertEqual(result.language, "zh")
        self.assertEqual(result.uk_phonetic, "")
        self.assertEqual(result.us_phonetic, "")
        self.assertEqual(result.senses, (youdao_lookup.Sense("", "你好 您好"),))

    def test_parse_ce_uses_target_i_text_without_appending_hash_tran(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "你好",
            {
                "ce": {
                    "word": [{
                        "return-phrase": {"l": {"i": "你好"}},
                        "trs": [
                            {
                                "tr": [{
                                    "l": {
                                        "i": [
                                            "",
                                            {
                                                "#text": "hello",
                                                "@action": "link",
                                                "@href": "app:ds:hello",
                                            },
                                        ],
                                        "#tran": "喂，你好（用于问候或打招呼）；",
                                    }
                                }]
                            },
                            {
                                "tr": [{
                                    "l": {
                                        "i": [{"#text": "hi", "@action": "link"}],
                                        "#tran": "嗨！（表示问候）；",
                                    }
                                }]
                            },
                        ],
                    }]
                }
            },
        )

        self.assertEqual(
            result.senses,
            (youdao_lookup.Sense("", "hello"), youdao_lookup.Sense("", "hi")),
        )

    def test_parse_ec_uses_i_definition_without_sentence_metadata_or_markup(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "how are you today",
            {
                "simple": {"word": [{"return-phrase": "how are you today"}]},
                "ec": {"word": [{"trs": [{"tr": [{"l": {
                    "sentence": [{
                        "enShow": "<b>How are you today</b>?",
                        "en": "How are you today?",
                        "type": "双语例句-《精编例句》",
                        "zh": "你今天怎么样？",
                    }],
                    "i": ["你今天怎么样：一种用于询问对方当天情况的问候语。"],
                }}]}]}]},
            },
        )

        self.assertEqual(
            result.senses,
            (youdao_lookup.Sense("", "你今天怎么样：一种用于询问对方当天情况的问候语。"),),
        )
        self.assertNotIn("<b>", result.senses[0].text)
        self.assertNotIn("双语例句", result.senses[0].text)

    def test_parse_chinese_query_prefers_ce_senses_when_simple_is_also_present(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "你好",
            {
                "simple": {"word": [{"return-phrase": "hello"}]},
                "ce": {"word": [{
                    "return-phrase": "你好",
                    "trs": [{"tr": [{"l": {"i": ["hello"]}}]}],
                }]},
                "web_trans": {"web-translation": [{"trans": [{"value": "网络释义"}]}]},
            },
        )

        self.assertEqual(result.language, "zh")
        self.assertEqual(result.headword, "你好")
        self.assertEqual(result.senses, (youdao_lookup.Sense("", "hello"),))
        self.assertEqual(result.fallback_translations, ())

    def test_parse_english_uses_ec_phonetics_when_simple_omits_them(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "hello",
            {
                "simple": {"word": [{"return-phrase": "hello"}]},
                "ec": {"word": [{
                    "ukphone": "həˈləʊ",
                    "usphone": "həˈloʊ",
                    "trs": [{"tr": [{"l": {"i": ["你好"]}}]}],
                }]},
            },
        )

        self.assertEqual(result.uk_phonetic, "həˈləʊ")
        self.assertEqual(result.us_phonetic, "həˈloʊ")

    def test_parse_uses_network_translations_only_when_dictionary_senses_are_absent(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "unknown",
            {
                "web_trans": {
                    "web-translation": [
                        {"trans": [{"value": "网络释义"}, {"value": "web meaning"}]}
                    ]
                }
            },
        )

        self.assertEqual(result.senses, ())
        self.assertEqual(result.fallback_translations, ("网络释义", "web meaning"))

    def test_parse_does_not_use_network_translations_when_another_dictionary_section_has_senses(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "hello",
            {
                "ce": {"word": [{"trs": [{"tr": [{"l": {"i": ["你好"]}}]}]}]},
                "web_trans": {"web-translation": [{"trans": [{"value": "网络释义"}]}]},
            },
        )

        self.assertEqual(result.fallback_translations, ())

    def test_parse_preserves_order_while_removing_exact_duplicates(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "echo",
            {
                "simple": {
                    "word": [{
                        "return-phrase": "echo",
                        "wfs": [
                            {"wf": {"name": "复数", "value": "echoes"}},
                            {"wf": {"name": "复数", "value": "echoes"}},
                            {"wf": {"name": "过去式", "value": "echoed"}},
                        ],
                    }]
                },
                "ec": {"word": [{"trs": [
                    {"pos": "n.", "tr": [{"l": {"i": ["回声"]}}]},
                    {"pos": "n.", "tr": [{"l": {"i": ["回声"]}}]},
                    {"pos": "v.", "tr": [{"l": {"i": ["回响"]}}]},
                ]}]},
            },
        )

        self.assertEqual(
            result.senses,
            (youdao_lookup.Sense("n.", "回声"), youdao_lookup.Sense("v.", "回响")),
        )
        self.assertEqual(
            result.forms,
            (youdao_lookup.WordForm("复数", "echoes"), youdao_lookup.WordForm("过去式", "echoed")),
        )

    def test_parse_normalizes_mixed_word_translation_and_recursive_pos_nodes(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "mix",
            {
                "simple": {
                    "word": [
                        None,
                        "not-a-word-object",
                        {
                            "return-phrase": {"#text": "mix"},
                            "wfs": [None, "ignored", {"wf": {"name": "过去式", "value": "mixed"}}],
                        },
                    ]
                },
                "ec": {
                    "word": [
                        None,
                        "ignored",
                        {
                            "trs": [
                                None,
                                "直接释义",
                                {"#text": "字典自身文本"},
                                {
                                    "pos": [{"#text": "v."}],
                                    "tr": {"l": {"i": "嵌套释义"}},
                                },
                            ]
                        },
                    ]
                },
                "ce": None,
                "web_trans": "ignored-section",
            },
        )

        self.assertEqual(result.headword, "mix")
        self.assertEqual(
            result.senses,
            (
                youdao_lookup.Sense("", "直接释义"),
                youdao_lookup.Sense("", "字典自身文本"),
                youdao_lookup.Sense("v.", "嵌套释义"),
            ),
        )
        self.assertEqual(result.forms, (youdao_lookup.WordForm("过去式", "mixed"),))

    def test_parse_normalizes_mixed_web_translation_shapes_with_stable_dedupe(self):
        youdao_lookup = load_module()

        result = youdao_lookup.parse_dictionary_result(
            "fallback",
            {
                "simple": None,
                "ec": "ignored-section",
                "ce": None,
                "web_trans": {
                    "web-translation": [
                        None,
                        "ignored-entry",
                        {
                            "trans": [
                                None,
                                "直接网络释义",
                                {"value": "值释义"},
                                {"value": {"#text": "递归值释义"}},
                                {"#text": "节点自身释义"},
                                "直接网络释义",
                            ]
                        },
                    ]
                },
            },
        )

        self.assertEqual(
            result.fallback_translations,
            ("直接网络释义", "值释义", "递归值释义", "节点自身释义"),
        )

    def test_only_non_object_explicit_word_structure_becomes_invalid_item_and_run_json(self):
        youdao_lookup = load_module()
        payload = {"simple": {"word": [None, "broken"]}}

        items = youdao_lookup.build_items(
            "hello",
            youdao_lookup.load_config({}),
            fetcher=lambda _query, _config: payload,
        )
        output = youdao_lookup.run(
            ["hello"],
            env={},
            fetcher=lambda _query, _config: payload,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "有道词典响应无效")
        self.assertFalse(items[0]["valid"])
        self.assertEqual(json.loads(output), {"items": items})

    def test_fetch_payload_uses_utf8_fixed_request_and_positive_configured_timeout(self):
        youdao_lookup = load_module()
        calls = []

        class Headers:
            def get_content_charset(self):
                return None

        class Response:
            headers = Headers()

            def read(self):
                return '{"simple": {}}'.encode("utf-8")

        @contextmanager
        def urlopen(request, timeout):
            calls.append((request, timeout))
            yield Response()

        payload = youdao_lookup.fetch_payload(
            "你好 world",
            youdao_lookup.Config(keyword="yd", timeout_seconds=2.5),
            opener=urlopen,
        )

        request, timeout = calls[0]
        self.assertEqual(payload, {"simple": {}})
        self.assertEqual(timeout, 2.5)
        self.assertEqual(urlparse(request.full_url).netloc, "dict.youdao.com")
        self.assertEqual(parse_qs(urlparse(request.full_url).query)["q"], ["你好 world"])
        self.assertTrue(request.get_header("User-agent").startswith("alfred-youdao-dictionary/"))

    def test_build_items_emits_headword_senses_forms_modifiers_and_quick_look(self):
        youdao_lookup = load_module()

        def fetcher(query, config):
            self.assertEqual(query, "run")
            self.assertEqual(config.timeout_seconds, 5.0)
            return {
                "simple": {"word": [{
                    "return-phrase": "run",
                    "ukphone": "rʌn",
                    "usphone": "rʌn",
                    "wfs": [{"wf": {"name": "过去式", "value": "ran"}}],
                }]},
                "ec": {"word": [{"trs": [
                    {"pos": "v.", "tr": [{"l": {"i": ["跑；运行"]}}]},
                    {"pos": "n.", "tr": [{"l": {"i": ["跑步"]}}]},
                ]}]},
            }

        items = youdao_lookup.build_items(" run ", youdao_lookup.load_config({}), fetcher=fetcher)

        self.assertEqual(
            [item["title"] for item in items],
            ["英 [rʌn]  美 [rʌn]", "v. 跑", "v. 运行", "n. 跑步", "过去式 ran"],
        )
        self.assertEqual(
            items[0]["subtitle"],
            "⌘↩ 播放英式发音  ·  ⌥↩ 播放美式发音",
        )
        self.assertEqual(
            json.loads(items[0]["arg"]),
            {"action": "copy", "text": "英 [rʌn]  美 [rʌn]"},
        )
        self.assertEqual(items[0]["icon"], {"path": "icon-pronunciation.png"})
        self.assertEqual(json.loads(items[1]["arg"]), {"action": "copy", "text": "v. 跑"})
        self.assertEqual(items[1]["text"]["copy"], "v. 跑")
        self.assertEqual(
            json.loads(items[0]["mods"]["cmd"]["arg"]),
            {"action": "pronounce", "text": "run", "accent": "uk"},
        )
        self.assertEqual(
            json.loads(items[0]["mods"]["alt"]["arg"]),
            {"action": "pronounce", "text": "run", "accent": "us"},
        )
        self.assertEqual(
            {item["quicklookurl"] for item in items},
            {"https://dict.youdao.com/result?word=run&lang=en"},
        )

    def test_build_items_splits_version_noun_sense_into_copyable_rows(self):
        youdao_lookup = load_module()

        def fetcher(_query, _config):
            return {
                "simple": {"word": [{"return-phrase": "version"}]},
                "ec": {"word": [{"trs": [{
                    "pos": "n.",
                    "tr": [{"l": {"i": [
                        "（同一种物件稍有不同的）样式，型号；"
                        "（从不同角度的）说法，描述；"
                        "（电影、剧本、乐曲等的）版本，改编形式；"
                        "《圣经》译本；胎位倒转术"
                    ]}}],
                }]}]},
            }

        items = youdao_lookup.build_items(
            "version", youdao_lookup.load_config({}), fetcher=fetcher
        )
        expected_titles = [
            "n. （同一种物件稍有不同的）样式，型号",
            "n. （从不同角度的）说法，描述",
            "n. （电影、剧本、乐曲等的）版本，改编形式",
            "n. 《圣经》译本",
            "n. 胎位倒转术",
        ]

        self.assertEqual([item["title"] for item in items], expected_titles)
        self.assertEqual(
            [json.loads(item["arg"])["text"] for item in items],
            expected_titles,
        )

    def test_english_without_phonetics_omits_the_pronunciation_row(self):
        youdao_lookup = load_module()

        items = youdao_lookup.build_items(
            "hello",
            youdao_lookup.load_config({}),
            fetcher=lambda _query, _config: {
                "simple": {"word": [{"return-phrase": "hello"}]},
                "ec": {"word": [{"trs": ["你好"]}]},
            },
        )

        self.assertEqual([item["title"] for item in items], ["你好"])
        self.assertNotIn("mods", items[0])
        self.assertNotIn("icon", items[0])

    def test_empty_input_returns_one_invalid_usage_item_without_fetching(self):
        youdao_lookup = load_module()

        def fetcher(_query, _config):
            self.fail("empty input must not make a request")

        items = youdao_lookup.build_items("   ", youdao_lookup.load_config({}), fetcher=fetcher)

        self.assertEqual(items, [{
            "title": "有道翻译",
            "subtitle": "请输入要翻译的内容",
            "valid": False,
        }])

    def test_file_selection_paths_are_rejected_before_fetching(self):
        youdao_lookup = load_module()

        for query in (
            "/Users/alice/Documents/secret-project-name.pdf",
            "file:///Users/alice/Documents/secret-project-name.pdf",
            "/Users/alice/Documents/one.txt\n/Users/alice/Documents/two.txt",
        ):
            with self.subTest(query=query):
                requests = []
                items = youdao_lookup.build_items(
                    query,
                    youdao_lookup.load_config({}),
                    fetcher=lambda value, _config: requests.append(value) or {},
                )

                self.assertEqual(requests, [])
                self.assertEqual(items, [{
                    "title": "不支持查询文件路径",
                    "subtitle": "请先选中文本，再使用 Hotkey 查询",
                    "valid": False,
                }])

    def test_unsupported_letter_scripts_are_rejected_before_fetch_without_pronunciation_modifiers(self):
        youdao_lookup = load_module()

        for query in ("こんにちは", "カタカナ", "안녕", "γειά", "你好かな"):
            with self.subTest(query=query):
                requests = []
                items = youdao_lookup.build_items(
                    query,
                    youdao_lookup.load_config({}),
                    fetcher=lambda value, _config: requests.append(value) or {},
                )

                self.assertEqual(requests, [])
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["title"], "仅支持中文和英文")
                self.assertFalse(items[0]["valid"])
                self.assertNotIn("mods", items[0])

    def test_chinese_and_english_punctuation_do_not_change_supported_language_route(self):
        youdao_lookup = load_module()
        calls = []

        def fetcher(query, _config):
            calls.append(query)
            if "你" in query:
                return {"ce": {"word": [{"trs": ["hello"]}]}}
            return {"ec": {"word": [{"trs": ["你好"]}]}}

        chinese_items = youdao_lookup.build_items(
            "你好，世界！", youdao_lookup.load_config({}), fetcher=fetcher
        )
        english_items = youdao_lookup.build_items(
            "hello, world! 123", youdao_lookup.load_config({}), fetcher=fetcher
        )
        punctuation_items = youdao_lookup.build_items(
            "123！？", youdao_lookup.load_config({}), fetcher=fetcher
        )

        self.assertEqual(calls, ["你好，世界！", "hello, world! 123", "123！？"])
        self.assertNotIn("mods", chinese_items[0])
        self.assertNotIn("mods", english_items[0])
        self.assertNotIn("mods", punctuation_items[0])

    def test_unknown_word_returns_one_valid_row_that_opens_the_youdao_result(self):
        youdao_lookup = load_module()

        items = youdao_lookup.build_items(
            "zzz",
            youdao_lookup.load_config({}),
            fetcher=lambda _query, _config: {},
        )

        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["valid"])
        self.assertEqual(items[0]["title"], "未找到 “zzz”")
        self.assertEqual(items[0]["subtitle"], "按回车在有道词典中打开")
        self.assertEqual(json.loads(items[0]["arg"]), {"action": "open", "query": "zzz"})
        self.assertEqual(items[0]["quicklookurl"], "https://dict.youdao.com/result?word=zzz&lang=en")

    def test_timeout_and_invalid_response_return_distinct_invalid_diagnostic_items(self):
        youdao_lookup = load_module()

        timeout_items = youdao_lookup.build_items(
            "hello",
            youdao_lookup.load_config({}),
            fetcher=lambda _query, _config: (_ for _ in ()).throw(youdao_lookup.LookupError("timed out")),
        )
        malformed_items = youdao_lookup.build_items(
            "hello",
            youdao_lookup.load_config({}),
            fetcher=lambda _query, _config: (_ for _ in ()).throw(youdao_lookup.InvalidResponseError("not JSON")),
        )

        self.assertEqual(timeout_items, [{
            "title": "有道词典请求失败",
            "subtitle": "timed out",
            "valid": False,
        }])
        self.assertEqual(malformed_items, [{
            "title": "有道词典响应无效",
            "subtitle": "not JSON",
            "valid": False,
        }])

    def test_fetch_payload_rejects_timeout_malformed_and_non_object_responses(self):
        youdao_lookup = load_module()

        def timeout_urlopen(_request, timeout):
            self.assertEqual(timeout, 5.0)
            raise TimeoutError("timed out")

        with self.assertRaises(youdao_lookup.LookupError):
            youdao_lookup.fetch_payload(
                "hello", youdao_lookup.load_config({}), opener=timeout_urlopen
            )

        class Response:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc_value, _traceback):
                return False

            def read(self):
                return self.body

        with self.assertRaises(youdao_lookup.InvalidResponseError):
            youdao_lookup.fetch_payload(
                "hello",
                youdao_lookup.load_config({}),
                opener=lambda _request, timeout: Response(b"not json"),
            )

        with self.assertRaises(youdao_lookup.InvalidResponseError):
            youdao_lookup.fetch_payload(
                "hello",
                youdao_lookup.load_config({}),
                opener=lambda _request, timeout: Response(b"[]"),
            )

        with self.assertRaises(youdao_lookup.InvalidResponseError):
            youdao_lookup.fetch_payload(
                "hello",
                youdao_lookup.load_config({}),
                opener=lambda _request, timeout: Response(b"\xff"),
            )

    def test_lookup_production_redirect_handler_rejects_cross_host_and_https_downgrade(self):
        youdao_lookup = load_module()
        handler = youdao_lookup.RejectRedirectHandler()
        production_handlers = youdao_lookup.production_opener().__self__.handlers
        request = youdao_lookup.urllib.request.Request(
            "https://dict.youdao.com/jsonapi?q=hello"
        )

        self.assertTrue(
            any(isinstance(item, youdao_lookup.RejectRedirectHandler) for item in production_handlers)
        )

        for destination in (
            "https://evil.example/collect",
            "http://dict.youdao.com/jsonapi?q=hello",
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

    def test_lookup_redirect_failure_maps_to_non_actionable_request_failure_item(self):
        youdao_lookup = load_module()

        def rejecting_opener(_request, timeout):
            self.assertEqual(timeout, 5.0)
            raise urllib.error.HTTPError(
                "https://evil.example/collect", 302, "Redirects are not allowed", {}, None
            )

        items = youdao_lookup.build_items(
            "hello",
            youdao_lookup.load_config({}),
            fetcher=lambda query, config: youdao_lookup.fetch_payload(
                query, config, opener=rejecting_opener
            ),
        )

        self.assertEqual(items[0]["title"], "有道词典请求失败")
        self.assertFalse(items[0]["valid"])

    def test_chinese_query_omits_the_pronunciation_row_and_modifier(self):
        youdao_lookup = load_module()
        items = youdao_lookup.build_items(
            "你好",
            youdao_lookup.load_config({}),
            fetcher=lambda _query, _config: {"ce": {"word": [{"trs": [
                {"tr": [{"l": {"i": ["hello"]}}]}
            ]}]}},
        )

        self.assertEqual([item["title"] for item in items], ["hello"])
        self.assertNotIn("mods", items[0])
        self.assertNotIn("icon", items[0])

    def test_chinese_quick_look_uses_youdao_english_dictionary_route(self):
        youdao_lookup = load_module()
        items = youdao_lookup.build_items(
            "今天天气很好我们一起出去玩吧",
            youdao_lookup.load_config({}),
            fetcher=lambda _query, _config: {},
        )

        self.assertEqual(
            items[0]["quicklookurl"],
            "https://dict.youdao.com/result?"
            "word=%E4%BB%8A%E5%A4%A9%E5%A4%A9%E6%B0%94%E5%BE%88%E5%A5%BD"
            "%E6%88%91%E4%BB%AC%E4%B8%80%E8%B5%B7%E5%87%BA%E5%8E%BB%E7%8E%A9%E5%90%A7&lang=en",
        )

    def test_run_serializes_alfred_items_with_an_injected_fetcher(self):
        youdao_lookup = load_module()

        output = youdao_lookup.run(
            ["web"],
            env={},
            fetcher=lambda _query, _config: {
                "web_trans": {"web-translation": [{"trans": [{"value": "网络"}]}]}
            },
        )

        self.assertEqual(json.loads(output)["items"][0]["subtitle"], "网络翻译")


if __name__ == "__main__":
    unittest.main()
