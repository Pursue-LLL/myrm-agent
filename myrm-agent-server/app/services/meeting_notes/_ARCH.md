# services/meeting_notes 模块架构

## 架构概述

会议音频听记编排服务层。将上传的长音频（会议/访谈）经分片并行转写（复用 `channels/voice/stt.py` 多供应商 STT 层）、LLM 纪要蒸馏（决议/争论点/Action Items 结构化提取）、发布为 wiki raw Markdown，并可选经 Obsidian portability 层审批回写用户 Vault。**编排层不实现任何 ASR/LLM/发布算法**——全部委托既有模块，本层只做场景化调度与数据装配。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `models.py` | 核心模型 | 会议纪要强类型模型：分片任务、转录片段、结构化纪要、发布结果 | ✅ |
| `service.py` | 核心服务 | 分片调度 + 并行转写 + LLM 纪要蒸馏 + wiki raw 发布编排门面；导出可复用的 `distill_meeting_notes` / `publish_meeting_notes` | ✅ |
| `live_notes.py` | 核心服务 | 会中实时链路：消费 final 转录 -> 防抖分段 -> 滚动结构化纪要（复用 `distill_meeting_notes`）与会话注册表 | ✅ |

## 关键依赖

- `app.channels.voice.stt`（复用 5 供应商转写 + fallback，禁止重复实现 ASR）
- `app.services.wiki.source_sync.publish_helpers`（frontmatter 构造与 wiki raw 发布）
- `app.services.wiki.vault.service`（archiver/vault 结构访问）
- `myrm_agent_harness.toolkits.wiki.core.compiler`（WikiStructure）

## 边界

- **实时 vs 批处理双轨**：`service.py` 为文件导入批处理管线；`live_notes.py` 为会中实时增量链路（消费流式转录 -> 防抖分段 -> 滚动结构化纪要）。二者共享 `distill_meeting_notes` 与 wiki 发布，但输入来源与调度相互解耦。
- **发布契约规范**：`publish_meeting_notes` 仅返回真实写入（`written=True`）的库相对路径（Vault-relative path，如 `meeting-notes/*.md`），绝不泄露宿主机绝对路径，对安全拦截或跳过的结果返回空列表。
- **同名不丢会议**：目标文件已存在时按 `-2`/`-3`… 自动改用空闲文件名（`_free_meeting_note_path`），避免 LLM 同名标题被 raw gate 跳过而导致整场会议静默丢失。
- **转录幂等**：`LiveNotesSession.ingest` 接受 `line_id`，重复 id 视为重投直接忽略（去重窗口 `_DEDUPE_WINDOW` 有界），保证 at-least-once 投递下逐字稿不重复。
- **时间戳防污染**：`ingest` 在唯一写入点用 `math.isfinite` 钳制非有限值——`inf // 60` 会得到 NaN 并在 `render_transcript` 抛错，进而让 finalize 500、整场会议纪要丢失。
- **LLM 载荷强转**：`distill_meeting_notes` 经 `_as_title` / `_as_text_tuple` / `_as_action_items` 归一化——真实模型会把单条列表写成裸字符串（否则逐字符炸成 23 条“风险”）、把“无”写成 `null`（否则 TypeError）、甚至返回非对象 JSON（否则 AttributeError）；非对象载荷与非法 JSON 同样降级为原文摘要，绝不让模型啰嗦变成会议失败。
- **≠** 声纹识别模型管理：diarization 委托 STT 供应商能力（xAI 云端已支持；本地 pyannote 为后续可配增强，不在本层硬编码）。
- **≠** 会议日历/预约调度。