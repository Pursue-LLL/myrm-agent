# services/artifacts/share/

## 架构概述

工件分享（artifact share）域：分享 bundle 打包、分享登记、无状态分享令牌的签发与校验、分享链接的统一创建、Markdown 工件分享页的渲染；`__init__.py` 为聚合门面，外部 import 经由门面。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出分享 bundle/registry/token/create/Markdown 页能力 | ✅ |
| `markdown_page.py` | 模块 | Markdown 工件的分享页：入口文件的媒体类型是 `text/markdown`（含按文档类型判定的无后缀入口）时，经分享页共用的 markdown-it 管线（`core/security/share/share_markdown.py`）渲染成带主题样式的整页，页面按访客语言写页脚、不含脚本，由路由配 `MARKDOWN_SHARE_CSP`；超过 256 KB 的文件不渲染（路由回落为原文），渲染在工作线程里做；浅 / 深两套主题下正文、链接、行内代码、代码块、引用与页脚对比度均 ≥ 4.5，由 `tests/services/artifacts/test_markdown_page.py` 钉住 | ✅ |
| `share_bundle.py` | 模块 | 分享 bundle 打包：聚合工件元数据与内容，生成可分发 bundle | ✅ |
| `share_create.py` | 模块 | 分享链接创建服务：签发令牌 → 物化 bundle 快照 → 登记，分享对话框与 IM 按钮共用这一条路径，所以每条发出的链接都能在分享管理里列出和撤销；快照失败不登记（不留无快照的链接），登记失败统一抛 `ShareRegistrationError`；调用方必须声明 `source`（分享对话框 / IM 按钮），成功后记一条 `share_created` | ✅ |
| `share_registry.py` | 模块 | 分享登记：分享记录 CRUD、链接管理、失效控制；公开入口门禁把未登记的令牌与已撤销的令牌同样拒绝（未登记且令牌体可解码时记 WARNING，只含令牌短指纹） | ✅ |
| `share_token.py` | 模块 | 无状态分享令牌签发/校验（防篡改、限时生效） | ✅ |
