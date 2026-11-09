# general_agent/tool_setup/

## 架构概述

GeneralAgent 工具装配：每个工具族一个 mixin，`mixin.py` 按固定顺序组合，`base.py` 只声明宿主属性，`common.py` 放无状态辅助。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `ToolSetupMixin` 与媒体/澄清门禁判定（`_should_mount_ask_question_tool`、`_configured_media_api_key`、`_media_gateway_configured`、`_is_media_credential_configured`、`_video_generation_credential_configured`、`_get_artifact_push_fn`），后者供测试逐分支覆盖 | ✅ |
| `mixin.py` | 组合 | 按固定 MRO 组合各工具族 | ✅ |
| `base.py` | 基类 | `ToolSetupBaseMixin` + TYPE_CHECKING 宿主属性 | ✅ |
| `common.py` | 支撑 | 媒体凭据/图片约束/artifact push、浏览器下载配置（工作区 `.agent/downloads`，以解析后的工作区根为不跟随链接的受信根；页面自发的下载仅在权限策略对 `download_url` 判 ALLOW 时放行）等模块级辅助 | ✅ |
| `skill.py` | 工具族 | 技能市场、技能管理 | ✅ |
| `search.py` | 工具族 | 搜索/抓取、澄清 | ✅ |
| `media.py` | 工具族 | 图像、视频、TTS | ✅ |
| `cron.py` | 工具族 | Cron | ✅ |
| `memory.py` | 工具族 | 记忆 | ✅ |
| `browser.py` | 工具族 | 浏览器、验证码；会话带下载支持（配置来自 `common.py`） | ✅ |
| `artifact.py` | 工具族 | Artifact 发布 | ✅ |
| `computer.py` | 工具族 | 桌面控制 | ✅ |

## 依赖关系

- `artifact.py` → `base.py`
- `browser.py` → `base.py`
- `browser.py` → `common.py`
- `computer.py` → `base.py`
- `computer.py` → `common.py`
- `cron.py` → `base.py`
- `media.py` → `base.py`
- `media.py` → `common.py`
- `memory.py` → `base.py`
- `mixin.py` → `artifact.py`
- `mixin.py` → `browser.py`
- `mixin.py` → `computer.py`
- `mixin.py` → `cron.py`
- `mixin.py` → `media.py`
- `mixin.py` → `memory.py`
- `mixin.py` → `search.py`
- `mixin.py` → `skill.py`
- `search.py` → `base.py`
- `search.py` → `common.py`
- `skill.py` → `base.py`
