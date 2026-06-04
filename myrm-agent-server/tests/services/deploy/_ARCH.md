# tests/services/deploy 模块架构

---

## 架构概述

产物部署业务层回归测试。覆盖静态打包、Vercel 客户端 mock、HTML 依赖 BFS 与 macOS 路径解析。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_deploy_packager.py` | 核心 | 单文件/目录收集、HTML 兄弟 CSS、node_modules 排除、未 resolve 根路径 |
| `test_vercel_client.py` | 核心 | deploy SPA 注入、projectId redeploy、状态轮询与 HTTP 错误 |

---

## 依赖关系

- `app.services.deploy.deploy_packager`
- `app.services.deploy.vercel_client`
