# scripts/ci/ 模块架构

CI 门禁脚本与 baseline 数据。由 GitHub Actions 与 `run_architecture_gates.sh` 调用。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `run_architecture_gates.sh` | 核心 | 串联 fractal docs、line budget、architecture pytest |
| `file_line_budget_baseline.txt` | 数据 | 已 grandfather 的超标 Python 模块路径（相对 server 根） |

## 运行

```bash
bash scripts/ci/run_architecture_gates.sh
```
