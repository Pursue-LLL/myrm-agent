# services/meeting_notes 模块架构

## 架构概述

会议听记编排服务层。会中把流式 STT 的 final 转录行滚动蒸馏为结构化纪要（决议/争论点/风险/Action Items），会议结束时发布为 wiki raw Markdown。**编排层不实现任何 ASR/LLM/发布算法**——全部委托既有模块，本层只做场景化调度与数据装配。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `models.py` | 核心模型 | 会议纪要强类型模型：待办项与结构化纪要 | ✅ |
| `service.py` | 核心服务 | LLM 纪要蒸馏与 wiki raw 发布编排门面；导出 `distill_meeting_notes` / `publish_meeting_notes` | ✅ |
| `live_notes.py` | 核心服务 | 会中实时链路：消费 final 转录 -> 防抖分段 -> 滚动结构化纪要（复用 `distill_meeting_notes`）与会话注册表 | ✅ |

## 关键依赖

- `app.services.wiki.source_sync.publish_helpers`（frontmatter 构造与 wiki raw 发布）
- `myrm_agent_harness.toolkits.wiki`（`WikiStructure`：raw 路径与重名检测）

## 边界

- **单条实时链路**：`live_notes.py` 在会中逐行消费 final 转录并滚动蒸馏；会议结束时由 finalize 路由经 `publish_meeting_notes` 发布。本层不读音频文件，也不做转写。
- **知识库范围由调用方定**：`publish_meeting_notes` 写入调用方传入的 `WikiStructure`；按智能体选择知识库由路由依赖 `get_scoped_wiki_archiver`（`agent_id` 查询参数）完成，本层不再接收智能体标识。
- **发布契约规范**：`publish_meeting_notes` 仅返回真实写入（`written=True`）的库相对路径（Vault-relative path，如 `meeting-notes/*.md`），绝不泄露宿主机绝对路径，对安全拦截或跳过的结果返回空列表。
- **同名不丢会议**：目标文件已存在时按 `-2`/`-3`… 自动改用空闲文件名（`_free_meeting_note_path`），避免 LLM 同名标题被 raw gate 跳过而导致整场会议静默丢失。
- **转录幂等**：`LiveNotesSession.ingest` 接受 `line_id`，重复 id 视为重投直接忽略（去重窗口 `_DEDUPE_WINDOW` 有界），保证 at-least-once 投递下逐字稿不重复。
- **时间戳防污染**：`ingest` 在唯一写入点用 `math.isfinite` 钳制非有限值——`inf // 60` 会得到 NaN 并在 `render_transcript` 抛错，进而让 finalize 500、整场会议纪要丢失。
- **LLM 载荷强转**：`distill_meeting_notes` 经 `_as_title` / `_as_text_tuple` / `_as_action_items` 归一化——真实模型会把单条列表写成裸字符串（否则逐字符炸成 23 条“风险”）、把“无”写成 `null`（否则 TypeError）、甚至返回非对象 JSON（否则 AttributeError）；非对象载荷与非法 JSON 同样降级为原文摘要，绝不让模型啰嗦变成会议失败。
- **≠** 声纹识别 / 说话人分离：本层只消费已转写的文本行。
- **≠** 会议日历/预约调度。
