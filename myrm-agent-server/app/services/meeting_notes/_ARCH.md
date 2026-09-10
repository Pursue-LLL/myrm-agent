# services/meeting_notes 模块架构

## 架构概述

会议音频听记编排服务层。将上传的长音频（会议/访谈）经分片并行转写（复用 `channels/voice/stt.py` 多供应商 STT 层）、LLM 纪要蒸馏（决议/争论点/Action Items 结构化提取）、发布为 wiki raw Markdown，并可选经 Obsidian portability 层审批回写用户 Vault。**编排层不实现任何 ASR/LLM/发布算法**——全部委托既有模块，本层只做场景化调度与数据装配。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `models.py` | 核心模型 | 会议纪要强类型模型：分片任务、转录片段、结构化纪要、发布结果 | ✅ |
| `service.py` | 核心服务 | 分片调度 + 并行转写 + LLM 纪要蒸馏 + wiki raw 发布编排门面 | ✅ |

## 关键依赖

- `app.channels.voice.stt`（复用 5 供应商转写 + fallback，禁止重复实现 ASR）
- `app.services.wiki.source_sync.publish_helpers`（frontmatter 构造与 wiki raw 发布）
- `app.services.wiki.vault.service`（archiver/vault 结构访问）
- `myrm_agent_harness.toolkits.wiki.core.compiler`（WikiStructure）

## 边界

- **≠** 实时流式听记（直播/边说边转）：本层为文件导入批处理管线。
- **≠** 声纹识别模型管理：diarization 委托 STT 供应商能力（xAI 云端已支持；本地 pyannote 为后续可配增强，不在本层硬编码）。
- **≠** 会议日历/预约调度。