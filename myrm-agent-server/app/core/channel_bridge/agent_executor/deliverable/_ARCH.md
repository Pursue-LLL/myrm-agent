# core/channel_bridge/agent_executor/deliverable/

## 架构概述

交付域子包：IM 渠道超限交付物的统一处理（附件上限、渐进压缩、路径扫描、深链按钮）。上游依赖 `core/artifacts/processor.py` Local 模式对超大可分享工件 emit artifacts 事件（reference-only persist）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 交付域门面：聚合导出 media / scanner / deep_links 的对外能力。 | ✅ |
| `media.py` | 模块 | 渠道附件大小上限统一常量 + 超限图片渐进压缩，供 artifact 事件与路径扫描两链路复用。 | ✅ |
| `scanner.py` | 模块 | Channel 回复（及 cron 产出）正文 workspace 路径扫描 → IM 原生附件（跳过 code block/inline code；workspace 沙箱内解析）；超限图片压缩降级（压缩副本为 `ephemeral` 附件，由消息总线删除）、超限文件提示；`append_deliverable_notes` 把超限/压缩提示按用户语言追加到正文（回复终稿与 cron 投递共用）。 | ✅ |
| `deep_links.py` | 模块 | 可分享 artifact 的 IM 附件收集（含超限压缩/深链/提示三态，压缩副本为 `ephemeral` 附件；缺失 file_path / ingress / version_id 打 WARNING） + 深链 ActionButton 生成（每个 artifact 一行一个按钮、最多 `MAX_SHARE_BUTTONS`（5，限制一条回复带的链接行数，多出的 artifact 仍以附件送达），出站管线按行遍历、裸按钮会让它抛 TypeError；经 `services/artifacts/share/share_create` 创建并登记，来源标注为 `ShareSource.IM`，与分享对话框同一路径，所以能在分享管理里列出和撤销；按钮只是附加，不取代附件与超限提示）+ DB version 批量查询。 | ✅ |

## 测试

- `tests/core/channel_bridge/test_deliverable_collect.py` — artifact 收集（可分享追踪、超限深链/压缩/提示三态、多交付物、空文件跳过）
- `tests/core/channel_bridge/test_deliverable_deep_links.py` — 深链按钮构建（单个与多个 artifact 的标签与 URL、没有版本的 artifact 不出按钮、经分享服务登记、无会话工作区时回落到运行根、数量上限；含：返回的行能通过出站管线的组件降级）
- `tests/core/channel_bridge/test_deliverable_deep_links_degradation.py` — 链接建不成时的失败兜底：无 artifact、无入口地址、无版本、某个 artifact 缺 version_id、数据库不可用、分享创建失败，都只丢链接（返回空或少一行）、不抛错；缺入口地址、无版本、缺 version_id、数据库不可用与单个分享创建失败还断言 WARNING 日志
- `tests/core/channel_bridge/test_deliverable_artifact_versions.py` — 最新版本号批量查询
- `tests/core/channel_bridge/test_deliverable_scanner.py` — 路径扫描、超限压缩/提示与文本剥离
- `tests/core/channel_bridge/test_deliverable_media.py` — 附件大小上限格式化与渐进压缩（透明保留、失败回退）
