# message-actions/

## 架构概述

消息操作菜单（复制、分支、反馈等）与文件变更撤销。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `Copy.tsx` | 组件 | 复制消息 Markdown/纯文本 | ✅ |
| `ExtractToSkillButton.tsx` | 组件 | 一键提炼 assistant 消息为可复用技能（通过 /learn 命令触发技能进化管线） | ✅ |
| `ExportMenu.tsx` | 组件 | 导出单条/会话为 Markdown/PDF 等 | ✅ |
| `MemoryFeedback.tsx` | 组件 | 记忆召回质量 thumbs up/down 反馈 | ✅ |
| `ReadAloud.tsx` | 组件 | TTS 朗读 assistant 消息（browser 默认本地 SpeechSynthesis；API 模式走 `/tts`，受 `voice_interaction` feature gate 隐藏） | ✅ |
| `RegenerateMenu.tsx` | 组件 | 重新生成/换模型/regenerate 分支菜单 | ✅ |
| `RevertFiles.tsx` | 组件 | 消息级文件变更撤销（每条 AI 回复旁） | ✅ |
| `SessionRevertButton.tsx` | 组件 | 会话级一键撤销所有 AI 文件变更（调用 POST /files/revert/session） | ✅ |
| `SaveEvalCase.tsx` | 组件 | 保存为 Eval Lab 用例 | ✅ |
| `SaveToMemoryButton.tsx` | 组件 | 一键保存 assistant 消息到长期记忆（调用 createMemory API） | ✅ |
| `SaveToWikiButton.tsx` | 组件 | 保存到 Wiki 知识库 | ✅ |
| `SiblingNav.tsx` | 组件 | 同 prompt 多分支 sibling 导航（←/→） | ✅ |
| `SourcesButton.tsx` | 组件 | 消息来源 Sheet 面板（web/mcp/conversation 三种类型差异化展示与操作） | ✅ |
| `Undo.tsx` | 组件 | 撤销上一条 user 发送（编辑重发入口） | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
