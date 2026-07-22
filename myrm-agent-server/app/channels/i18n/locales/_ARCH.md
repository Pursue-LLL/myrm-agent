# channels/i18n/locales/

## 架构概述

渠道 i18n 本地化资源（JSON + Fluent）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `en.ftl` | 数据 | 英文 Fluent 翻译（渠道命令回复、系统消息、WebUI 后台 bash 完成通知 `bash_bg_finish_*`、Goal stream 失败通知 `goal_stream_failed_*`、Agent picker 提示、预算拦截消息） | — |
| `zh-CN.ftl` | 数据 | 简体中文 Fluent 翻译（含 `bash_bg_finish_*`、`goal_stream_failed_*`） | — |
| `zh-TW.ftl` | 数据 | 繁体中文 Fluent 翻译（基于 zh-CN.ftl OpenCC s2twp 转换） | — |
| `ja.ftl` | 数据 | 日文 Fluent 翻译（基于 en.ftl 全量翻译） | — |
| `de.json` | 数据 | 德文 JSON 翻译（错误提示） | — |
| `en.json` | 数据 | 英文 JSON 翻译（错误提示） | — |
| `ja.json` | 数据 | 日文 JSON 翻译（错误提示） | — |
| `ko.json` | 数据 | 韩文 JSON 翻译（错误提示） | — |
| `zh-CN.json` | 数据 | 简体中文 JSON 翻译（错误提示） | — |
| `zh-TW.json` | 数据 | 繁体中文 JSON 翻译（基于 zh-CN.json OpenCC s2twp 转换） | — |
