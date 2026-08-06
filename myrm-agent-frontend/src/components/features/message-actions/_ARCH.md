# message-actions/

## 架构概述

消息操作菜单（复制、分支、反馈等）与文件变更撤销。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `Copy.tsx` | 组件 | 复制消息 Markdown/纯文本 | ✅ |
| `ExtractToSkillButton.tsx` | 组件 | 一键提炼 assistant 消息为可复用技能（发 raw `/learn`，由 server `rewrite_learn_query_if_needed` 接 SSOT）；Honest UX：`toast.info(started)` 表示已提交而非假成功 | ✅ |
| `ExportMenu.tsx` | 组件 | 导出单条/会话为 Markdown/PDF 等 | ✅ |
| `MemoryFeedback.tsx` | 组件 | 记忆召回质量 thumbs up/down 反馈 | ✅ |
| `ReadAloud.tsx` | 组件 | TTS 朗读 assistant 消息（browser 默认本地 SpeechSynthesis；API 模式走 `/tts`，受 `voice_interaction` feature gate 隐藏） | ✅ |
| `RegenerateMenu.tsx` | 组件 | 重新生成/换模型/regenerate 分支菜单 | ✅ |
| `SessionRevertButton.tsx` | 组件 | 会话级撤销（ChatWindow chips）：Honest UX 分流 + Tooltip + 混合成功 toast | ✅ |
| `RevertFiles.tsx` | 组件 | 消息级文件撤销：空变更/不可撤销 toast 分流；混合变更 Popover 标注 skip_reason；部分成功 toast | ✅ |
| `SaveEvalCase.tsx` | 组件 | 保存为 Eval Lab 用例 | ✅ |
| `SaveToMemoryButton.tsx` | 组件 | 一键保存 assistant 消息到长期记忆（调用 createMemory API） | ✅ |
| `SaveToWikiButton.tsx` | 组件 | Chat message ids → `POST /wiki/compound`（server DB hydrate Q&A/trust）→ Pending HITL（**agentConfig.agentId scoped**）；无痕模式隐藏；`message_not_found` / `incognito_forbidden` i18n toast；Vitest：`__tests__/SaveToWikiButton.scope.test.tsx` | ✅ |
| `SiblingNav.tsx` | 组件 | 同 prompt 多分支 sibling 导航（←/→） | ✅ |
| `SourcesButton.tsx` | 组件 | 独立消息来源 Sheet（web/mcp/knowledge/conversation）；knowledge 含 wiki asset 缩略图；导出 `SourceItem` 供 `MemoryCitationsButton` 复用 | ✅ |
| `Undo.tsx` | 组件 | 撤销上一条 user 发送（编辑重发入口） | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)

## 约束

- Chat→Wiki 写入 SSOT：与 `artifacts/ArtifactCard`、`research/ResearchOutputPanel` 一致，均传 `useChatStore.agentConfig.agentId`
