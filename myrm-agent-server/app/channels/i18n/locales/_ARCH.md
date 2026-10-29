# channels/i18n/locales/

## 架构概述

渠道 i18n 本地化资源（JSON + Fluent）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `en.ftl` | 数据 | 英文 Fluent 翻译（渠道命令回复、系统消息、WebUI 后台 bash 完成通知 `bash_bg_finish_*`、Goal stream 失败通知 `goal_stream_failed_*`、知识转正审批原因 `knowledge_patch_review_reason`、Agent picker 提示、预算拦截消息、附件降级/失败提示 `attachment_*_note`、异步委派（`/delegate`）的 `delegation_*`：四条流程回复（缺少任务、并发上限、已收到回执（附 `/stop` 取消提示）、补充指引已注入）与任务结束时的页眉和通知（`delegation_done` / `delegation_failed` / `delegation_timed_out` / `delegation_no_output` / `delegation_duration_minutes` / `delegation_duration_seconds`）、失败回合的成员安全错误文案 `error_*` 及仅可信所有者私聊使用的账户指引 `error_billing_owner` / `error_billing_owner_platform` / `error_auth_owner` / `error_model_not_found_owner`、loop guard 暂停回合的回复 `placeholder_tool_stuck_paused`、停机取消了正在运行的回合时发给该聊天的 `turn_interrupted_by_restart`（该回合不会重放，请对方重新发送），其余三份 `.ftl` 同步） | — |
| `zh-CN.ftl` | 数据 | 简体中文 Fluent 翻译（含 `bash_bg_finish_*`、`goal_stream_failed_*`） | — |
| `zh-TW.ftl` | 数据 | 繁体中文 Fluent 翻译（基于 zh-CN.ftl OpenCC s2twp 转换） | — |
| `ja.ftl` | 数据 | 日文 Fluent 翻译（基于 en.ftl 全量翻译） | — |
| `de.json` | 数据 | 德文 JSON 翻译（错误提示） | — |
| `en.json` | 数据 | 英文 JSON 翻译（错误提示） | — |
| `ja.json` | 数据 | 日文 JSON 翻译（错误提示） | — |
| `ko.json` | 数据 | 韩文 JSON 翻译（错误提示） | — |
| `zh-CN.json` | 数据 | 简体中文 JSON 翻译（错误提示） | — |
| `zh-TW.json` | 数据 | 繁体中文 JSON 翻译（基于 zh-CN.json OpenCC s2twp 转换） | — |
