"""Chinese LLM-facing static texts for memory_save_tool and memory_manage_tool.

Must stay semantically aligned with ``_memory_tool_texts_en``.

[INPUT]
(none: static text only)

[OUTPUT]
- MEMORY_SAVE_CORE_ZH: memory_save_tool description core (Chinese)
- MEMORY_SAVE_WRITE_TARGET_ZH: the write-target block of the save description, offered only under a shared-write policy
- MEMORY_MANAGE_TOOL_DESCRIPTION_ZH: memory_manage_tool description (Chinese)

[POS]
Chinese half of the memory tool description SSOT; composed by ``_memory_agent_tool_descriptions``.
"""

MEMORY_SAVE_CORE_ZH = """为用户存储新记忆。记忆跨会话持久化并注入未来对话，请保持条目紧凑、聚焦持久事实：一条可独立理解的陈述性事实。

**何时保存**（应主动执行）：
- 用户说「记住这个」「记一下」「别忘了」，或设定规则：「总是 X」「绝不 Y」
- 用户纠正你的行为或输出风格（Agent 行为修正，非已存事实纠错；见下）
- 用户分享稳定偏好、习惯或个人细节（姓名、角色、时区），或你发现用户环境/项目中短期内不会变的事实

**何时禁止使用本工具**：
- 已召回事实有误 → 使用 memory_manage_tool，action=correct（不要重复 save）
- 任务进度、会话结果、已完成工作日志，或临时状态（PR 号、commit SHA、当前文件路径、进行中的事项）
- 实时业务状态：订单/物流进度、余额、验证码/OTP、临时下载或排队链接 — 应查实时工具
- 一周内过时的信息、分步流程/工作流、原始数据转储/代码片段/冗长文本
- 工具提示重复时不要用相同内容重试

**归属与短暂状态**（关键）：绝不要把第三方（家人、同事）的特质、疾病或偏好归因给用户（如 "User's boss prefers dark mode"）；不要保存短暂情绪状态（如 "User is feeling anxious today"），除非用户明确说明是长期或慢性状况。

**类别指南**：
- knowledge：稳定事实（项目技术栈、环境细节）
- event：重要过往事件（如开始新项目）— 无需指定 importance 与 tags
- preference：用户喜好/厌恶
- rule：条件性行为规则（需 rule_trigger 如「写代码时」；可选 rule_priority）
- instruction：全局无条件指令（如「始终用中文回复」）— 不要设置 rule_trigger

**重要性**（0–1，仅 knowledge 生效，其他类别忽略）：0.8–1.0 用户明确要求记住该事实；0.5–0.7 推断的稳定事实；0.2–0.4 补充上下文。"""

# Appended to the save description only while the write policy allows shared writes.
MEMORY_SAVE_WRITE_TARGET_ZH = """**写入目标**：
- "bound"（默认）：仅当前 Agent 角色可见
- "shared"：跨 Agent 共享知识（姓名、时区等）"""

MEMORY_MANAGE_TOOL_DESCRIPTION_ZH = """更新、删除、纠正或评分已有记忆（memory_id 来自 memory_search_tool 结果）。

**何时使用**（不要用 memory_save_tool）：用户说「忘了那个」「不对」「删掉那条记忆」；召回的记忆过时或不准确（correct），或只需小幅措辞修正（update）；或用户确认某条记忆有帮助（rate：强化检索排序）。

**何时禁止使用本工具（转用其他工具/机制）**：
- 存储新事实、偏好或规则 → memory_save_tool
- 任务进度或聊天历史（不是记忆）
- [preference] 结果：profile 属性没有可管理的 id — 要修改请用 memory_save_tool 以相同的 preference_key 重新保存；Agent 不能删除偏好

**操作指南**：
- delete：删除记忆
- update：仅微调措辞或重要性 — 事实本身仍有效（如修正错别字「Pyhton」→「Python」）
- correct：用最新正确事实替换过时或错误事实（如「用户在旧金山」→「用户搬到了西雅图」）— 仅 knowledge 记忆；保留历史记录；纠正已有记忆时优先于 memory_save_tool
- rate：记录用户反馈 — 仅 knowledge 或 event 记忆；需要 rating_score 1-5（1=差，5=优）

用户保护（钉选或锁定）的记忆，Agent 不能更新、纠正或删除 — 请先请用户解除保护。"""
