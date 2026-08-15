# services/artifacts/share/

## 架构概述

工件分享（artifact share）域：分享 bundle 打包、分享登记、无状态分享令牌的签发与校验。由 `app/services/artifacts/` 平铺模块拆分而来，通过 `__init__.py` 门面聚合导出以保持外部 import 稳定。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出分享 bundle/registry/token 能力 | ✅ |
| `share_bundle.py` | 模块 | 分享 bundle 打包：聚合工件元数据与内容，生成可分发 bundle | ✅ |
| `share_registry.py` | 模块 | 分享登记：分享记录 CRUD、链接管理、失效控制 | ✅ |
| `share_token.py` | 模块 | 无状态分享令牌签发/校验（防篡改、限时生效） | ✅ |
