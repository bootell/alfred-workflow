# Youdao Dictionary

用 Alfred 的 `yd` 关键词查询有道词典；仅支持中文和英文。输入词、短语或英文句子后，结果按音标（若有）、释义、词形（或无结果提示）的顺序显示。同一词性的多个义项会按中文分号拆成多行，避免长释义在 Alfred 中显示为省略号。只有当 `ec/ce` 都没有词典释义时，才显示标记为“网络翻译”的 `web_trans` 兜底结果。

## 使用

- 普通回车：复制当前条目的完整可见标题。
- 英文且有音标时，首行使用带喇叭角标的图标，主标题显示左侧英式和右侧美式音标，副标题提示 `Cmd` 播放英式、`Option` 播放美式。
- 中文不显示发音行，缺少音标的英文不显示发音行。
- `Shift Quick Look`：查看该查询在有道结果页的 Quick Look。
- 没有结果时按回车，会在浏览器中打开有道结果页。

### Hotkey

工作流随附一个未绑定按键的 Hotkey：它的动作是 **Show Alfred**，Argument 选择 **macOS Selection**，并在所选文本前加入精确前缀 `{var:KEYWORD} `。导入后在 Alfred 工作流编辑器中选择该 Hotkey，点击热键录制区域设置你自己的组合键；然后选中文本并按该组合键即可进入查询。macOS Selection 也可能返回所选文件，但文件路径会在网络请求前被拒绝，不会发送给有道。

## 配置与依赖

- `KEYWORD`：触发关键词，默认 `yd`。
- `TIMEOUT_SECONDS`：网络超时秒数，默认 `5`；同时控制查询与发音请求。仅接受 `0 < TIMEOUT_SECONDS <= 60`，其他值回退为 `5`。
- 运行时是 `/usr/bin/python3`，仅使用 Python 标准库，没有第三方依赖或捆绑二进制文件。

## 网络、隐私与失败行为

查询文本会发送到有道的固定 HTTPS `https://dict.youdao.com/jsonapi` 接口，固定参数为 `q`、`doctype=json`、`jsonversion=2`、`client=mobile` 和 `dicts={"count":3,"dicts":[["ec"],["ce"],["web_trans"]]}`。`jsonapi` 是未公开接口，没有稳定性或 SLA 保证；它不是需要商务开通的官方 v2/dict 接口。发音使用 `https://dict.youdao.com/dictvoice`，无结果的结果页使用 `https://dict.youdao.com/result`，也都是外部 HTTPS 端点。网络适配器可替换，但 Alfred 的显示/动作协议不变。

所有外部地址都是固定 HTTPS `dict.youdao.com`，不接受任意 URL。查询与发音网络客户端都拒绝 HTTP 重定向，避免请求被带往其他主机或降级为 HTTP。`dictvoice` 固定携带 `audio=<查询文本>`：英文美式 `type=2`、英式 `type=1`；中文不显示发音行，也不生成中文发音动作。`result` 使用 URL 编码的 `word=<原查询>` 与 `lang`；Quick Look 与无结果 action 固定使用 `lang=en`，以覆盖英文词典和中英结果页。Hotkey 的 macOS Selection 若返回绝对路径、`file://` 或多文件路径，文件路径会在网络请求前被拒绝。

含平假名、片假名、韩文、希腊文等非拉丁且非汉字字母时，不支持的语种会在请求前返回不可操作的错误行，不发送网络请求。纯汉字文本按中文处理。

本工作流不持久化查询历史、释义或音频；音频只下载到临时文件播放，播放后立即删除。网络、响应或发音失败时，查询会显示失败条目，发音会显示 macOS 通知；不会自动粘贴、自动朗读、记录历史或写入生词本。
