#!/usr/bin/env python3
import json
import math
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass


DEFAULT_KEYWORD = "yd"
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 60.0
LOOKUP_ENDPOINT = "https://dict.youdao.com/jsonapi"
LOOKUP_DICTS = '{"count":3,"dicts":[["ec"],["ce"],["web_trans"]]}'
POS_PREFIX_RE = re.compile(
    r"^(n\.|v\.|vt\.|vi\.|adj\.|adv\.|prep\.|pron\.|conj\.|int\.|num\.|aux\.|art\.)(?:\s+|$)",
    re.IGNORECASE,
)


class LookupError(Exception):
    pass


class InvalidResponseError(ValueError):
    pass


class RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise urllib.error.HTTPError(
            new_url,
            code,
            "Redirects are not allowed",
            headers,
            file_pointer,
        )


@dataclass(frozen=True)
class Config:
    keyword: str
    timeout_seconds: float


@dataclass(frozen=True)
class Sense:
    pos: str
    text: str


@dataclass(frozen=True)
class WordForm:
    name: str
    value: str


@dataclass(frozen=True)
class DictionaryResult:
    query: str
    headword: str
    language: str
    uk_phonetic: str
    us_phonetic: str
    senses: tuple
    forms: tuple
    fallback_translations: tuple


def parse_timeout(value):
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return (
        timeout
        if math.isfinite(timeout) and 0 < timeout <= MAX_TIMEOUT_SECONDS
        else DEFAULT_TIMEOUT_SECONDS
    )


def load_config(env):
    return Config(
        keyword=str(env.get("KEYWORD", DEFAULT_KEYWORD)).strip() or DEFAULT_KEYWORD,
        timeout_seconds=parse_timeout(env.get("TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
    )


def build_lookup_url(query):
    parameters = {
        "q": query,
        "doctype": "json",
        "jsonversion": "2",
        "client": "mobile",
        "dicts": LOOKUP_DICTS,
    }
    return f"{LOOKUP_ENDPOINT}?{urllib.parse.urlencode(parameters)}"


def production_opener():
    return urllib.request.build_opener(RejectRedirectHandler()).open


def fetch_payload(query, config, opener=None):
    request = urllib.request.Request(
        build_lookup_url(query),
        headers={"User-Agent": "alfred-youdao-dictionary/1.0"},
    )
    open_request = production_opener() if opener is None else opener
    try:
        with open_request(request, timeout=parse_timeout(config.timeout_seconds)) as response:
            raw_payload = response.read().decode("utf-8")
    except UnicodeDecodeError as error:
        raise InvalidResponseError(str(error)) from error
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        raise LookupError(str(error)) from error
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
        raise InvalidResponseError(str(error)) from error
    if not isinstance(payload, dict):
        raise InvalidResponseError("Response JSON must be an object")
    return payload


def flatten_text(value):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [text for item in value for text in flatten_text(item)]
    if isinstance(value, dict):
        if "#text" in value:
            return flatten_text(value["#text"])
        return [
            text
            for key, item in value.items()
            if not key.startswith("@")
            for text in flatten_text(item)
        ]
    return []


def text_value(value):
    return " ".join(flatten_text(value)).strip()


def flatten_translation_text(value):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [text for item in value for text in flatten_translation_text(item)]
    if isinstance(value, dict):
        if "i" in value:
            return flatten_text(value["i"])
        if "#text" in value:
            return flatten_text(value["#text"])
        if "l" in value:
            return flatten_translation_text(value["l"])
    return []


def translation_text_value(value):
    return " ".join(flatten_translation_text(value)).strip()


def as_nodes(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def word_nodes(section):
    if not isinstance(section, dict) or "word" not in section:
        return ()
    raw_words = section["word"]
    candidates = raw_words if isinstance(raw_words, list) else [raw_words]
    words = tuple(item for item in candidates if isinstance(item, dict))
    if candidates and not words:
        raise InvalidResponseError("word must contain an object")
    return words


def first_word(section):
    words = word_nodes(section)
    return words[0] if words else {}


def unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def classify_query(query):
    has_chinese = False
    has_unsupported_letters = False
    for character in query:
        name = unicodedata.name(character, "")
        if name.startswith("CJK UNIFIED IDEOGRAPH") or name.startswith(
            "CJK COMPATIBILITY IDEOGRAPH"
        ):
            has_chinese = True
        elif unicodedata.category(character).startswith("L") and "LATIN" not in name:
            has_unsupported_letters = True
    if has_unsupported_letters:
        return "unsupported"
    return "zh" if has_chinese else "en"


def is_file_selection(query):
    value = (query or "").strip()
    return value.lower().startswith("file://") or os.path.isabs(value)


def parse_senses(section):
    senses = []
    for word in word_nodes(section):
        for translation in as_nodes(word.get("trs")):
            if isinstance(translation, dict):
                if "tr" in translation:
                    text = translation_text_value(translation["tr"])
                elif "tran" in translation:
                    text = translation_text_value(translation["tran"])
                elif "#text" in translation:
                    text = text_value(translation["#text"])
                else:
                    text = translation_text_value(translation)
            else:
                text = translation_text_value(translation)
            if text:
                pos = text_value(translation.get("pos")) if isinstance(translation, dict) else ""
                if not pos:
                    prefix = POS_PREFIX_RE.match(text)
                    if prefix:
                        pos = prefix.group(1)
                        text = text[prefix.end():].strip()
                if text:
                    senses.append(Sense(pos, text))
    return unique(senses)


def parse_forms(word):
    forms = []
    for item in as_nodes(word.get("wfs") if isinstance(word, dict) else None):
        form = item.get("wf") if isinstance(item, dict) else None
        if not isinstance(form, dict):
            continue
        name = text_value(form.get("name"))
        value = text_value(form.get("value"))
        if name and value:
            forms.append(WordForm(name, value))
    return unique(forms)


def parse_section_forms(section):
    return unique(
        form
        for word in word_nodes(section)
        for form in parse_forms(word)
    )


def parse_fallback_translations(section):
    translations = []
    if not isinstance(section, dict):
        return ()
    for entry in as_nodes(section.get("web-translation")):
        if not isinstance(entry, dict):
            continue
        for translation in as_nodes(entry.get("trans")):
            if isinstance(translation, dict) and "value" in translation:
                text = text_value(translation["value"])
            else:
                text = text_value(translation)
            if text:
                translations.append(text)
    return unique(translations)


def parse_dictionary_result(query, payload):
    if not isinstance(payload, dict):
        raise InvalidResponseError("Response JSON must be an object")

    normalized_query = (query or "").strip()
    simple_word = first_word(payload.get("simple"))
    ec_word = first_word(payload.get("ec"))
    ce_word = first_word(payload.get("ce"))
    english = classify_query(normalized_query) == "en"
    source_word = simple_word if english else ce_word
    headword = text_value(source_word.get("return-phrase")) or text_value(
        (ec_word if english else ce_word).get("return-phrase")
    ) or normalized_query
    ec_senses = parse_senses(payload.get("ec"))
    ce_senses = parse_senses(payload.get("ce"))
    senses = ec_senses if english else ce_senses
    return DictionaryResult(
        query=normalized_query,
        headword=headword,
        language="en" if english else "zh",
        uk_phonetic=(
            text_value(simple_word.get("ukphone")) or text_value(ec_word.get("ukphone"))
            if english else ""
        ),
        us_phonetic=(
            text_value(simple_word.get("usphone")) or text_value(ec_word.get("usphone"))
            if english else ""
        ),
        senses=senses,
        forms=unique((*parse_section_forms(payload.get("simple")), *parse_section_forms(payload.get("ec")))),
        fallback_translations=(
            () if ec_senses or ce_senses else parse_fallback_translations(payload.get("web_trans"))
        ),
    )


def compact_action(action, **values):
    return json.dumps({"action": action, **values}, ensure_ascii=False, separators=(",", ":"))


def build_result_url(query):
    return "https://dict.youdao.com/result?" + urllib.parse.urlencode(
        {"word": query, "lang": "en"}
    )


def copy_item(title, subtitle, quicklookurl):
    return {
        "title": title,
        "subtitle": subtitle,
        "arg": compact_action("copy", text=title),
        "valid": True,
        "text": {"copy": title, "largetype": title},
        "quicklookurl": quicklookurl,
    }


def phonetic_title(result):
    values = []
    if result.uk_phonetic:
        values.append(f"英 [{result.uk_phonetic}]")
    if result.us_phonetic:
        values.append(f"美 [{result.us_phonetic}]")
    return "  ".join(values)


def headword_item(result, quicklookurl):
    title = phonetic_title(result)
    if result.language != "en" or not title:
        return None
    item = copy_item(
        title,
        "⌘↩ 播放英式发音  ·  ⌥↩ 播放美式发音",
        quicklookurl,
    )
    item["icon"] = {"path": "icon-pronunciation.png"}
    item["mods"] = {
        "cmd": {"arg": compact_action("pronounce", text=result.query, accent="uk")},
        "alt": {"arg": compact_action("pronounce", text=result.query, accent="us")},
    }
    return item


def invalid_item(title, subtitle):
    return [{"title": title, "subtitle": subtitle, "valid": False}]


def no_result_item(result, quicklookurl):
    title = f"未找到 “{result.query}”"
    return [{
        "title": title,
        "subtitle": "按回车在有道词典中打开",
        "arg": compact_action("open", query=result.query),
        "valid": True,
        "quicklookurl": quicklookurl,
    }]


def build_items(query, config, fetcher=fetch_payload):
    normalized_query = (query or "").strip()
    if not normalized_query:
        return invalid_item("有道翻译", "请输入要翻译的内容")
    if is_file_selection(normalized_query):
        return invalid_item("不支持查询文件路径", "请先选中文本，再使用 Hotkey 查询")
    if classify_query(normalized_query) == "unsupported":
        return invalid_item(
            "仅支持中文和英文",
            "请输入中文汉字、拉丁字母、数字或标点",
        )
    try:
        payload = fetcher(normalized_query, config)
    except LookupError as error:
        return invalid_item("有道词典请求失败", str(error))
    except InvalidResponseError as error:
        return invalid_item("有道词典响应无效", str(error))
    try:
        result = parse_dictionary_result(normalized_query, payload)
    except ValueError as error:
        return invalid_item("有道词典响应无效", str(error))
    quicklookurl = build_result_url(result.query)
    if not result.senses and not result.fallback_translations:
        return no_result_item(result, quicklookurl)
    items = []
    pronunciation = headword_item(result, quicklookurl)
    if pronunciation:
        items.append(pronunciation)
    for sense in result.senses:
        meanings = [text.strip() for text in sense.text.split("；") if text.strip()]
        for meaning in meanings:
            title = f"{sense.pos} {meaning}".strip()
            items.append(copy_item(title, "释义", quicklookurl))
    for translation in result.fallback_translations:
        items.append(copy_item(translation, "网络翻译", quicklookurl))
    if result.forms:
        items.append(
            copy_item(
                "；".join(f"{form.name} {form.value}" for form in result.forms),
                "词形变化",
                quicklookurl,
            )
        )
    return items


def run(argv=None, env=None, fetcher=fetch_payload):
    args = sys.argv[1:] if argv is None else argv
    query = args[0] if args else ""
    config = load_config(os.environ if env is None else env)
    return json.dumps(
        {"items": build_items(query, config, fetcher=fetcher)},
        ensure_ascii=False,
    )


def main(argv=None):
    sys.stdout.write(run(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
