# Alfred Workflows

A small collection of Alfred workflows for everyday developer utilities.

## Workflows

### JSON Formatter

Parse JSON or Python literal text, repeatedly unwrap nested JSON strings, write the final value as a formatted `.json` file, and open it in the browser.

- Keyword: `json`
- Package: `json-formater/json-formater.alfredworkflow`
- Source: `json-formater/workflow/`

Examples:

```text
json {"a":1}
```

```text
json
```

Running `json` without an argument reads the current clipboard.

### Time Converter

Convert Unix timestamps and time strings across configurable time zones.

- Keyword: `time`
- Package: `time-converter/time.alfredworkflow`
- Source: `time-converter/workflow/`

Examples:

```text
time
time 1700000000
time 1700000000000
time 2023-11-15 06:13:20
```

The workflow supports these Alfred user configuration values:

- `KEYWORD`: trigger keyword. Default: `time`
- `INPUT_TZ`: time zone used to parse time strings. Default: `Asia/Shanghai`
- `OUTPUT_TZS`: comma-separated output time zones. Default: `Asia/Shanghai`
- `TIME_FORMAT`: display format. Default: `YYYY-MM-DD HH:mm:ss`

### IP Lookup

Look up IP geolocation for IP addresses, domains, or the current public IP.

- Keyword: `ip`
- Package: `ip-lookup/ip-lookup.alfredworkflow`
- Source: `ip-lookup/workflow/`

Examples:

```text
ip
ip 8.8.8.8
ip 2001:4860:4860::8888
ip example.com
```

The workflow supports these Alfred user configuration values:

- `KEYWORD`: trigger keyword. Default: `ip`
- `LANGUAGE`: ip-api response language. Default: `zh-CN`
- `TIMEOUT_SECONDS`: network timeout in seconds. Default: `5`

IP Lookup returns location (`country regionName city district`), network items (`isp`, then `org`), and optional `IP Flags` (`mobile`, `proxy`, or `mobile / proxy`). For an empty query, the first item shows the current public IP address, followed by those same lookup details. Private or reserved IP ranges show only a single `private` or `reserved` item with the `IP Flags` subtitle.

### Youdao Dictionary

查询有道词典的中文和英文词、短语或英文句子。

- Keyword: `yd`
- Package: `youdao-dictionary/youdao-dictionary.alfredworkflow`
- Source: `youdao-dictionary/workflow/`

结果依次显示音标（若有）、释义和词形；同一词性的多个义项会按中文分号拆成多行，避免长释义在 Alfred 中显示为省略号。只有当 `ec/ce` 都没有词典释义时，才显示标记为“网络翻译”的 `web_trans` 兜底，覆盖短语和英文句子的查询。普通回车复制当前行的完整可见标题。英文且有音标时，首行使用带喇叭角标的图标，主标题显示左侧英式和右侧美式音标，副标题提示按 `Cmd` 播放英式、按 `Option` 播放美式。中文不显示发音行，缺少音标的英文不显示发音行。按 `Shift Quick Look` 可预览有道结果页；无结果时回车会打开结果页。

工作流提供一个未绑定的 Hotkey：导入后在 Alfred 工作流编辑器选中 Hotkey，设置热键；它会以 **Show Alfred** 打开 Alfred，使用 **macOS Selection** 并把所选文本加上 `{var:KEYWORD} ` 前缀。macOS Selection 也可能返回所选文件，但文件路径会在网络请求前被拒绝，不会发送给有道。

配置项只有：

- `KEYWORD`: trigger keyword. Default: `yd`
- `TIMEOUT_SECONDS`: network timeout in seconds. Default: `5`; 同时控制查询与发音请求，仅接受 `0 < TIMEOUT_SECONDS <= 60`，其他值回退为 `5`。

## Installation

1. Download the `.alfredworkflow` file for the workflow you want to use.
2. Open the file with Alfred.
3. Review the workflow configuration in Alfred, then import it.

The packaged workflow files are included in this repository:

- `json-formater/json-formater.alfredworkflow`
- `time-converter/time.alfredworkflow`
- `ip-lookup/ip-lookup.alfredworkflow`
- `youdao-dictionary/youdao-dictionary.alfredworkflow`

## Requirements

- macOS
- Alfred with workflow support
- Python 3 available at `/usr/bin/python3`

The workflows use only Python standard library modules.

## Development

Run the tests from the repository root:

```sh
python3 -m unittest discover -s json-formater/tests
python3 -m unittest discover -s time-converter/tests
python3 -m unittest discover -s ip-lookup/tests
python3 -m unittest discover -s youdao-dictionary/tests
```

Project layout:

```text
json-formater/
  workflow/          JSON Formatter source files
  tests/             JSON Formatter tests
  json-formater.alfredworkflow

time-converter/
  workflow/          Time Converter source files
  tests/             Time Converter tests
  time.alfredworkflow

ip-lookup/
  workflow/          IP Lookup source files
  tests/             IP Lookup tests
  ip-lookup.alfredworkflow

youdao-dictionary/
  workflow/          Youdao Dictionary source files
  tests/             Youdao Dictionary tests
  youdao-dictionary.alfredworkflow
```

## Privacy And Security

各 Workflow 的网络与数据处理各不相同，以下逐项说明；不要将它们概括为“全部不调用外部服务”。

JSON Formatter can read the current clipboard when triggered without an argument. It writes generated `.json` files under Alfred's workflow cache directory (`$alfred_workflow_cache`) when available. Cache cleanup is left to Alfred and macOS.

Time Converter reads only the query text and Alfred workflow configuration values needed for time-zone conversion.

IP Lookup sends the entered IP address, resolved domain IP address, or current public IP lookup request to the free ip-api.com JSON endpoint. The free endpoint uses HTTP, is rate limited, and is intended for non-commercial use.

Youdao Dictionary 仅支持中文和英文。查询文本会发送到固定 HTTPS `https://dict.youdao.com/jsonapi`，固定参数为 `q`、`doctype=json`、`jsonversion=2`、`client=mobile` 和 `dicts={"count":3,"dicts":[["ec"],["ce"],["web_trans"]]}`；这是未公开的 `jsonapi` 接口，没有稳定性或 SLA 保证，且不是需商务开通的官方 v2/dict 接口。网络适配器可替换，但 Alfred 的显示/动作协议不变。`https://dict.youdao.com/dictvoice` 和 `https://dict.youdao.com/result` 是发音和结果页的外部端点。本工作流不持久化查询历史、释义或音频；音频仅临时播放后删除。网络或响应失败时显示失败条目，发音失败时显示通知；不会自动粘贴、自动朗读、记录历史或写入生词本。运行时仅使用 `/usr/bin/python3` 和 Python 标准库。

Youdao Dictionary 的所有外部地址都是固定 HTTPS `dict.youdao.com`，不接受任意 URL。查询与发音网络客户端都拒绝 HTTP 重定向，避免请求被带往其他主机或降级为 HTTP。`dictvoice` 固定携带 `audio=<查询文本>`：英文美式 `type=2`、英式 `type=1`；中文不显示发音行，也不生成中文发音动作。`result` 使用 URL 编码的 `word=<原查询>` 与 `lang`；Quick Look 与无结果 action 固定使用 `lang=en`，以覆盖英文词典和中英结果页。Hotkey 的 macOS Selection 若返回绝对路径、`file://` 或多文件路径，文件路径会在网络请求前被拒绝。含平假名、片假名、韩文、希腊文等非拉丁且非汉字字母时，不支持的语种会在请求前返回不可操作的错误行，不发送网络请求；纯汉字文本按中文处理。

## License

No license has been declared yet. Until a license is added, all rights are reserved by default.
