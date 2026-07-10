# message-input-actions/

## 架构概述

输入框附件、语音、斜杠命令等扩展操作。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ActiveWorkingMemoryPanel.tsx` | 组件/模块 | — | — |
| `AgentIndicator.tsx` | 组件/模块 | — | — |
| `AgentToolsToggle.tsx` | 组件/模块 | — | — |
| `AttachButton.tsx` | 组件 | 文件附件按钮：Tauri 走原生对话框 / Web 走 `<input type="file">`；支持 image/video/audio/doc/text；含模型能力检查、SHA-256 去重、视频 100MB / 音频 25MB 大小校验 | ✅ |
| `AttachList.tsx` | 组件 | 附件预览列表：ImageThumbnail（含 Lightbox + ImageEditor 标注，失败 toast）/ VideoThumbnail / FilePill | ✅ |
| `BaseModelSelector.tsx` | 组件/模块 | — | — |
| `CameraInputButton.tsx` | 组件/模块 | — | — |
| `CameraPreview.tsx` | 组件/模块 | — | — |
| `DeepSearchToggle.tsx` | 组件/模块 | — | — |
| `EnvironmentShield.tsx` | 组件/模块 | — | — |
| `FileIconSVG.tsx` | 组件/模块 | — | — |
| `FocusFlushButton.tsx` | 组件/模块 | — | — |
| `GoalModeToggle.tsx` | 组件/模块 | — | — |
| `ImageLightbox.tsx` | 组件/模块 | — | — |
| `IncognitoModeToggle.tsx` | 组件/模块 | — | — |
| `SandboxModeToggle.tsx` | 组件/模块 | 沙箱模式切换：Agent 模式下可见，一键隔离 workspace 到 git worktree | — |
| `SearchModeSelector.tsx` | 组件/模块 | 分段式模式选择器：Fast / Agent / Deep Research / Consensus，含 feature gate 门控和搜索服务校验 | ✅ |
| `SpeechInputButton.tsx` | 组件/模块 | — | — |
| `ThinkingIntensityButton.tsx` | 组件/模块 | — | — |
| `ToolsPanel.tsx` | 组件/模块 | — | — |
| `VisionCapabilityNotice.tsx` | 组件/模块 | — | — |
| `VoiceSessionButton.tsx` | 组件/模块 | — | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
