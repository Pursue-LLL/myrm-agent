# services/memory/evidence 模块架构

## 架构概述

记忆证据溯源、上下文切片回放与代码仓库历史证据服务。
提供零模型成本（0 LLM Calls）的端到端证据锚定与审计：
- 对话上下文切片回放（`EvidencePlaybackService`）；
- 仓库近期提交与变更证据摘要提取（`RepoHistoryDigestService`）；
- 严格敏感凭据脱敏过滤（`redact_sensitive`）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 导出 | 导出 `EvidencePlaybackService` 与 `RepoHistoryDigestService` | ✅ |
| `playback_service.py` | 核心 | 对话上下文切片提取与脱敏（支持 WebUI 与多渠道消息双轨穿透） | ✅ |
| `repo_digest_service.py` | 核心 | 仓库提交历史与变更证据摘要服务（桥接 Harness Git 提炼算子） | ✅ |
