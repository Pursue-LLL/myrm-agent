# channels/types/ 模块架构

## 架构概述

渠道域纯类型定义（无 I/O）：消息信封、会话策略、通知模式、UI 组件与 ReplyContext 结构化引用。Reply/Quote 协议详见 [REPLY_CONTEXT_DESIGN.md](REPLY_CONTEXT_DESIGN.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 类型包导出 | — |
| `messages.py` | 核心 | 跨渠道消息数据结构（MediaType: IMAGE/DOCUMENT/AUDIO/VIDEO/CONTACT, MediaAttachment（`ephemeral`=临时文件由消息总线在送达终态后删除）, guess_media_type, RenderStyle 等） | ✅ |
| `topics.py` | 核心 | 话题路由类型（TopicContext、ReplyMode、DraftTimeoutAction、IdentityScopeMode） | ✅ |
| `streaming.py` | 核心 | Agent 执行流事件（ProgressUpdate、StreamingText、FissionTopologyNode/Update） | ✅ |
| `voice.py` | 核心 | 语音 STT/TTS 配置与结果（VoiceConfig、TTSMode、STTResult） | ✅ |
| `components.py` | 核心 | 跨渠道交互组件（按钮、快捷回复等）类型 | ✅ |
| `session.py` | 核心 | 会话标识与隔离策略 | ✅ |
| `notification.py` | 核心 | 通知模式枚举与显式 @ 元数据 | ✅ |
| `status.py` | 核心 | 渠道状态、StartMode 与诊断类型 | ✅ |
| `thread_sharing.py` | 核心 | 话题级 thread 共享/隔离模式 | ✅ |
