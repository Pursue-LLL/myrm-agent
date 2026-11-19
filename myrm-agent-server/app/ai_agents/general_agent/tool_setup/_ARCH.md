# general_agent/tool_setup/

## 架构概述

GeneralAgent 工具装配：每个工具族一个 mixin，`mixin.py` 按固定顺序组合，`base.py` 声明宿主属性并提供用户与 Agent 安全配置的合并读取与工具描述语言的解析，`common.py` 放无状态辅助。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `ToolSetupMixin` 与媒体/澄清门禁判定（`_should_mount_ask_question_tool`、`_configured_media_api_key`、`_media_gateway_configured`、`_is_media_credential_configured`、`_video_generation_credential_configured`），后者供测试逐分支覆盖 | ✅ |
| `mixin.py` | 组合 | 按固定 MRO 组合各工具族 | ✅ |
| `base.py` | 基类 | `ToolSetupBaseMixin`：TYPE_CHECKING 宿主属性，以及用户与 Agent 安全配置的合并读取 `_merged_security_config`（浏览器的域名名单与 `web_fetch` 的网络黑名单共用）；工具描述语言的解析 `_tool_description_locale`（会话语言，没有则取渠道的默认语言，再没有取环境变量 `MYRM_LOCALE`，最后是英文；`factory/builder.py` 的 goal 工具与 `skill.py`、`search.py`、`memory.py` 里提供中英描述的工具都调它，调用点不自行取值） | ✅ |
| `common.py` | 支撑 | 媒体凭据、已存引擎设置到配置值的转换（密钥成 `SecretStr`、网关成 `ToolGatewayConfig`）、图片约束、浏览器下载配置（工作区 `.agent/downloads`，以解析后的工作区根为不跟随链接的受信根；页面自发的下载仅在权限策略对 `download_url` 判 ALLOW 时放行）等模块级辅助 | ✅ |
| `skill.py` | 工具族 | 技能市场、技能管理（描述与管理结果里的撤销提示按 `_tool_description_locale` 选中英文） | ✅ |
| `search.py` | 工具族 | 搜索/抓取、澄清（`web_fetch`、`web_search`、`ask_question` 的描述语言取 `_tool_description_locale`）；`web_fetch` 的网络黑名单以每次调用求值的函数传入（池化 Agent 的策略在每轮对话前重新加载，不能在建工具时定死） | ✅ |
| `media.py` | 工具族 | 图像、视频、TTS：用户已选择（模型 / 供应商 / 音色，`core.media.selection`）且凭据就绪才挂载，不补默认值；文件引用的允许根取 `declared_allowed_roots` | ✅ |
| `cron.py` | 工具族 | Cron | ✅ |
| `memory.py` | 工具族 | 记忆（工具描述语言取 `_tool_description_locale`） | ✅ |
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
