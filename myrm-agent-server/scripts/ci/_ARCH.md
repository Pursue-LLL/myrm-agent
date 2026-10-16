# scripts/ci/ 模块架构

CI 门禁脚本与 baseline 数据。由 GitHub Actions 与 `run_architecture_gates.sh` 调用。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `check_profile_capability_escalation.py` | 核心 | AST 静态审计内置安全配置与 Agent 模板，阻断 PR 越权与提权放宽 |
| `lib_harness_deps.sh` | 核心 | 共享 harness 感知 `uv sync`（本地树 / PyPI） |
| `run_architecture_gates.sh` | 核心 | 串联 fractal docs、md-refs 反引号引用校验（`validate_arch_inventory.py --md-refs`，本地 harness 源码模式生效）、导入可解析性门禁（harness `check_import_resolvability.py`：`app/` 内每条 `app.*` / `myrm_agent_harness.*` import 须指向真实模块与名字；harness 源码在旁时生效，PyPI 模式显式跳过）、模块可达性门禁（harness `check_module_reachability.py --server --base`：diff 模式，仅当本次改动使 server 单元失去生产调用方才失败；基线修订取 `MYRM_REACHABILITY_BASE`，默认 `origin/main`，无法确定时报错而非放行；harness 源码在旁时生效，PyPI 模式显式跳过）、profile capability 门禁、ruff lint、`promtool check rules`、architecture pytest |
| `run_default_tests.sh` | 核心 | ruff lint + 默认 pytest 套件（`-m 'not e2e and not performance' -n0`；CI `server-unit-tests.yml`） |
| `run_locked_use_tests.sh` | 核心 | Locked Use / Privacy Curtain 聚焦 pytest（`tests/services/locked_use/` + `test_desktop_locked_use_diagnostic.py`；CI job `locked-use-pytest`） |
| `file_line_budget_baseline.txt` | 数据 | 已超过 400 行的 Python 模块路径台账（相对 server 根；由 `check_file_line_budget.py --write-baseline` 维护，非 CI 阻断项） |

## 运行

```bash
bash scripts/ci/run_architecture_gates.sh
bash scripts/ci/run_default_tests.sh
```
