# scripts 模块架构

运维、部署、门禁与 CLI 工具集。所有脚本均为独立入口，不被 `app/` 业务代码引用。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| deploy.py | 核心 | 统一部署入口（tauri/sandbox/docker 三模式） | ✅ |
| deploy_pkg/ | 核心 | 部署子包：actions/checks/constants/docker_core/modes/postgres/utils | ✅ |
| cli.py | 核心 | Myrm CLI 配置管理工具（config validate 等） | ✅ |
| check_fractal_docs.py | 门禁 | 分形文档合规检查（校验 `app/**` 目录均含 `_ARCH.md`） | ✅ |
| run_myrm_core_coverage_gate.sh | 门禁 | Harness 核心搜索+上下文路径覆盖率 ≥80% 门禁 | ✅ |
| cleanup_qdrant_locks.py | 运维 | 清理 Qdrant 嵌入式模式残留锁文件（运行时自动调用） | ✅ |
| init-age.sql | 运维 | Apache AGE 扩展初始化（PostgreSQL 图数据库） | ✅ |

---

## 依赖关系

```
scripts/ ──→ app/ (仅 deploy.py 和部分运维脚本导入 app 模块)
         ──→ myrm-agent-harness (check_fractal_docs.py 扫描 harness _ARCH.md)
```

- 所有脚本均为独立入口，不被 `app/` 反向引用
- `deploy_pkg/` 是 `deploy.py` 的内部子包，不对外暴露
- `cleanup_qdrant_locks.py` 被 `app/core/retriever/vector/defaults.py` 在运行时动态导入
