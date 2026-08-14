# services/kanban/task_runner/

KanbanTaskRunner 执行域。`runner.py` 为编排入口；`stream.py` 附件与 multimodal；`worktree.py` Git 隔离（分支唯一化 + 终态 merge 回目标分支）；`_worktree_merge.py` merge 前置 git 步骤（自动提交/可合并判断/target 分支切换）；`profile.py` agent profile 解析。聚合出口见 `__init__.py`。上级 SSOT：`../_ARCH.md`。

## worktree.py 分支隔离设计

- **唯一工作分支**：每个任务创建独立 worktree 分支 `{target_branch}-{task_id[:8]}`（`_worktree_branch_name`），杜绝并行任务共享分支时的 `git worktree add -B` 强制 reset 数据丢失与隔离失效。
- **分支名消毒**：`_sanitize_git_branch` 统一替换 git 非法字符（空格/`~^:?*[\`/`..`/首尾 `-`），非法分支名不再静默 fallback 到错误目录。
- **终态 merge 闭环**：`merge_task_worktree` 在任务 COMPLETED 时（`move_orchestrator` 手动路径 + `dispatcher_lifecycle` task_completed 钩子）把唯一分支 `--no-ff` merge 回目标分支，成功后清理 worktree 目录并删除唯一分支；merge 冲突时保留 worktree 与分支供人工处理（绝不静默丢提交）。
- **显式 target 分支**：`_worktree_merge._ensure_target_branch_checked_out` 在 merge 前把 base_dir 切换到任务声明的 `task.branch`（首用从 HEAD 创建），保证 merge 落在用户指定分支而非当前 checkout 分支。
- **防丢数据**：`_worktree_merge._auto_commit_dirty_worktree` 返回 worktree 是否干净；自动提交被拒（如 pre-commit hook）时 `merge_task_worktree` 返回 False 并**保留 worktree**，agent 未提交编辑绝不静默删除。
- **cleanup 保数据**：`cleanup_worktree`（ARCHIVED/FAILED）只移除 worktree 目录，**保留**唯一分支上的提交；分支删除仅在 merge 成功之后。
