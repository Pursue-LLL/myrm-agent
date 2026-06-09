# scripts 模块架构

运维、部署、门禁与 CLI 工具集。所有脚本均为独立入口，不被 `app/` 业务代码引用。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| deploy.py | 核心 | 统一部署入口（tauri/sandbox/docker 三模式） | ✅ |
| deploy_pkg/ | 核心 | 部署子包：actions/checks/constants/docker_core/modes/postgres/utils | ✅ |
| cli.py | 核心 | Myrm CLI 配置管理工具（config validate 等） | ✅ |
| check_fractal_docs.py | 门禁 | 分形文档合规（`app/**` 目录 `_ARCH.md`；`--strict-headers` + baseline；`--no-stub` 守卫 `api/` 与 `channels/providers/`） | ✅ |
| check_file_line_budget.py | 门禁 | 禁止新增超过 400 行的 Python 模块（`scripts/ci/file_line_budget_baseline.txt` grandfather 存量） | ✅ |
| sync_arch_file_tables.py | 工具 | 从文件头 POS/模块 docstring 刷新 stub `_ARCH.md` 文件表（`--path-prefix` / `--force`） | ✅ |
| run_myrm_core_coverage_gate.sh | 门禁 | Harness 核心搜索+上下文路径覆盖率 ≥80% 门禁 | ✅ |
| cleanup_qdrant_locks.py | 运维 | 清理 Qdrant 嵌入式模式残留锁文件（运行时自动调用） | ✅ |
| init-age.sql | 运维 | Apache AGE 扩展初始化（PostgreSQL 图数据库） | ✅ |
| dev/profile_test_memory.py | 工具 | 按 test 文件测量 peak RSS（macOS `time -l`） | ✅ |
| dev/run_tests_low_memory.sh | 工具 | 本地低内存 pytest（`-n0`；`PYTEST_XDIST_WORKERS=N`） | ✅ |
| ci/ | 门禁 | CI 脚本与 baseline（见 [ci/_ARCH.md](ci/_ARCH.md)） | ✅ |

---

## 依赖关系

```
scripts/ ──→ app/ (仅 deploy.py 和部分运维脚本导入 app 模块)
scripts/ci/ ──→ lib_harness_deps.sh（共享 harness uv sync）
scripts/ci/ ──→ run_architecture_gates.sh（fractal + line budget + architecture pytest）
scripts/ci/ ──→ run_default_tests.sh（默认 pytest；-m not e2e）
```

- 所有脚本均为独立入口，不被 `app/` 反向引用
- `deploy_pkg/` 是 `deploy.py` 的内部子包，不对外暴露
- `cleanup_qdrant_locks.py` 被 `app/core/retriever/vector/defaults.py` 在运行时动态导入
