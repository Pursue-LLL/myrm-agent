# wiki/portability

## 架构概述

Deterministic full-vault ZIP export for `WikiStructure`. No Obsidian or HTTP dependencies.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `vault_archive.py` | 核心 | Walk `base_dir` (raw + wiki), exclude caches, emit manifest v2 ZIP | ✅ |
| `vault_git.py` | 核心 | Local `.git` init + auto-commit on vault mutations when `WikiConfig.enable_version_control`; every git command goes through `core.security.safe_git` so no hook, `core.fsmonitor` or filter named by a `.git` that arrived with the vault (or a repository nested below it) runs, and a vault config that cannot be neutralised, or a vault whose repository is not its own (`.git` is a symlink or a file naming another repository, a `commondir` file, a `core.worktree` that leaves the vault, a separate git directory — refused by the framework's layout proof, which `require_own_repository` runs once before `add -A`), is skipped as `unsafe_repository` instead of committing to another repository; a vault that is a linked worktree of another repository is snapshotted on its own branch | ✅ |
| `obsidian_canvas.py` | 核心 | 纯文件格式工具：JSON Canvas (.canvas) 文本节点提取、[[Wikilinks]] 解析（经 `core.link_extraction`，代码块内不算链接）与 1-Hop 依赖展开 | ✅ |
| `__init__.py` | 入口 | Public exports (`build_vault_archive_zip`, `commit_vault_git_snapshot`, `extract_canvas_text_nodes`, …) | ✅ |

Server `myrm-agent-server/app/services/wiki/obsidian/export.py` adds `.obsidian/graph.json` and README on top of this archive.
