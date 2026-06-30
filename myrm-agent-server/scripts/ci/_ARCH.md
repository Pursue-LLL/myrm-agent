# scripts/ci/ 模块架构

CI 门禁脚本与 baseline 数据。由 GitHub Actions 与 `run_architecture_gates.sh` 调用。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `lib_harness_deps.sh` | 核心 | 共享 harness 感知 `uv sync`（本地树 / PyPI） |
| `run_architecture_gates.sh` | 核心 | 串联 fractal docs、line budget、architecture pytest |
| `run_default_tests.sh` | 核心 | 默认 pytest 套件（`-m 'not e2e and not performance' -n0`；CI `server-unit-tests.yml`） |
| `file_line_budget_baseline.txt` | 数据 | 已 grandfather 的超标 Python 模块路径（相对 server 根） |

## 运行

```bash
bash scripts/ci/run_architecture_gates.sh
bash scripts/ci/run_default_tests.sh
```
