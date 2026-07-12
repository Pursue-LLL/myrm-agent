# message-input-actions/

## 架构概述

输入框附件、语音、斜杠命令等扩展操作。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ActiveWorkingMemoryPanel.tsx` | 组件 | 当前会话 working memory 预览 Popover | ✅ |
| `AgentIndicator.tsx` | 组件 | 输入区当前 Agent 头像/名称指示 | ✅ |
| `AgentToolsToggle.tsx` | 组件 | Agent 工具开关快捷切换 | ✅ |
| `AttachButton.tsx` | 组件 | 文件附件按钮：Tauri 走原生对话框 / Web 走 `<input type="file">`；支持 image/video/audio/doc/text；含模型能力检查、SHA-256 去重、视频 100MB / 音频 25MB 大小校验 | ✅ |
| `AttachList.tsx` | 组件 | 附件预览列表：ImageThumbnail（含 Lightbox + ImageEditor 标注，失败 toast）/ VideoThumbnail / FilePill | ✅ |
| `BaseModelSelector.tsx` | 组件 | 基础模型快速选择下拉（非完整 model picker） | ✅ |
| `CameraInputButton.tsx` | 组件 | 摄像头拍照/录像输入按钮 | ✅ |
| `CameraPreview.tsx` | 组件 | 摄像头实时预览与 capture 控制 | ✅ |
| `DeepSearchToggle.tsx` | 组件 | Deep Research 模式开关 | ✅ |
| `EnvironmentShield.tsx` | 组件 | 环境变量/密钥泄露防护提示盾 | ✅ |
| `FileIconSVG.tsx` | 辅助 | 附件文件类型 SVG 图标 | ✅ |
| `FocusFlushButton.tsx` | 组件 | Focus 模式一键 flush 上下文按钮 | ✅ |
| `GoalModeToggle.tsx` | 组件 | Goal 模式开关 | ✅ |
| `ImageLightbox.tsx` | 组件 | 附件图片 Lightbox 全屏预览 | ✅ |
| `IncognitoModeToggle.tsx` | 组件 | 无痕/不写入记忆模式切换 | ✅ |
| `SandboxModeToggle.tsx` | 组件 | 沙箱模式切换：Agent 模式下可见，一键隔离 workspace 到 git worktree | ✅ |
| `SearchModeSelector.tsx` | 组件 | 分段式模式选择器：Fast / Agent / Deep Research / Consensus，含 feature gate 门控和搜索服务校验 | ✅ |
| `SessionSkillsToggle.tsx` | 组件 | 会话级 Skill 作用域切换：Agent 模式下 Popover 列出当前 Agent 绑定的 Skill（`agentConfig.selectedSkillIds`），用户 toggle 子集覆盖默认全量加载，PATCH `/session-skills` 持久化 | ✅ |
| `SpeechInputButton.tsx` | 组件 | 语音转文字输入按钮（STT） | ✅ |
| `ThinkingIntensityButton.tsx` | 组件 | 思考强度/推理预算调节 | ✅ |
| `ToolsPanel.tsx` | 组件 | 输入区工具/MCP 快捷面板 Popover | ✅ |
| `VisionCapabilityNotice.tsx` | 组件 | 当前模型无 Vision 能力时的提示条 | ✅ |
| `VoiceSessionButton.tsx` | 组件 | 全双工语音会话启动按钮 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
