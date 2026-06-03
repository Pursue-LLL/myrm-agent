# scripts/maintainer 模块架构

Harness 供应链与 vortexai 子模块维护。OSS 日常用户只用 `myrm setup`（PyPI）；本目录在 monorepo 或显式 `myrm harness` 时启用。

## 文件清单

| 文件 | 职责 |
|------|------|
| `setup.sh` | Monorepo 首次：submodule + editable harness + bun |
| `install_harness_dev.sh` | harness 安装（auto / pypi / source / editable） |
| `sync_harness_lock.sh` | PyPI 发版后刷新 `uv.lock` |
| `check_harness_pypi.py` | 发版前 PyPI 包存在性检查 |
| `init_submodules.sh` | `myrm submodules`：递归 init + drift 检测 |

## 入口

- `./myrm setup`（vortexai 根，设 `MYRM_MONOREPO_ROOT`）
- `myrm harness install | sync-lock`
- `myrm submodules`
