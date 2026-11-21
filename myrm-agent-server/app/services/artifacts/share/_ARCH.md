# services/artifacts/share/

## 架构概述

工件分享（artifact share）域：分享 bundle 打包、分享登记、无状态分享令牌的签发与校验、分享链接的统一创建；`__init__.py` 为聚合门面，外部 import 经由门面。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出分享 bundle/registry/token/create 能力 | ✅ |
| `share_bundle.py` | 模块 | 分享 bundle 打包：聚合工件元数据与内容，生成可分发 bundle | ✅ |
| `share_create.py` | 模块 | 分享链接创建服务：签发令牌 → 物化 bundle 快照 → 登记，分享对话框与 IM 按钮共用这一条路径，所以每条发出的链接都能在分享管理里列出和撤销；快照失败不登记（不留无快照的链接），登记失败统一抛 `ShareRegistrationError`；调用方必须声明 `source`（分享对话框 / IM 按钮），成功后记一条 `share_created` | ✅ |
| `share_registry.py` | 模块 | 分享登记：分享记录 CRUD、链接管理、失效控制；公开入口门禁把未登记的令牌与已撤销的令牌同样拒绝（未登记且令牌体可解码时记 WARNING，只含令牌短指纹） | ✅ |
| `share_token.py` | 模块 | 无状态分享令牌签发/校验（防篡改、限时生效） | ✅ |
