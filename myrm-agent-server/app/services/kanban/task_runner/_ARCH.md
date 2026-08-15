# services/kanban/task_runner/

KanbanTaskRunner 执行域。`runner.py` 为编排入口；`stream.py` 附件与 multimodal；`worktree.py` Git 隔离（分支唯一化 + 终态 merge 回目标分支 + per-base_dir merge 互斥）；`_worktree_merge.py` merge 前置 git 步骤（自动提交/可合并判断/target 分支切换/分支名校验）；`worktree_cleanup.py` worktree 目录与唯一分支的清理（safe 删除防丢数据）；`profile.py` agent profile 解析。共享 git 命令基础设施复用 `app.services.chat._git_shared`。聚合出口见 `__init__.py`。上级 SSOT：`../_ARCH.md`。

## worktree.py 分支隔离设计

- **唯一工作分支**：每个任务创建独立 worktree 分支 `{target_branch}-{task_id[:8]}`（`_worktree_branch_name`），杜绝并行任务共享分支时的 `git worktree add -B` 强制 reset 数据丢失与隔离失效。
- **分支名消毒**：`_sanitize_git_branch` 统一替换 git 非法字符（空格/`~^:?*[\`/`..`/首尾 `-`），非法分支名不再静默 fallback 到错误目录。
- **终态 merge 闭环**：`merge_task_worktree` 在任务 COMPLETED 时（`move_orchestrator` 手动路径 + `dispatcher_lifecycle` task_completed 钩子）把唯一分支 `--no-ff` merge 回目标分支，成功后清理 worktree 目录并删除唯一分支；merge 冲突时收集冲突文件列表 → `git merge --abort` 恢复 repo（防 MERGE_HEAD 阻塞后续 merge）→ 保留 worktree 与分支供人工处理（绝不静默丢提交），返回 `(False, [冲突文件])`。
- **merge 互斥**：同一 base_dir 的 merge 由共享的 `_git_shared._get_merge_lock` 串行化（kanban 与 sandbox merge 同 repo 并发曾观测到 "Unable to write index"），不同仓库并行。
- **git identity 兜底**：auto-commit 与 merge commit 前经 `_git_shared._git_identity` 检测 repo 是否配置 user 身份，未配置时注入 `-c user.name=Myrm Agent -c user.email=agent@myrm.local`（不污染全局/仓库配置），bare repo 上自动合并不再失败。
- **显式 target 分支**：`_worktree_merge._ensure_target_branch_checked_out` 在 merge 前把 base_dir 切换到任务声明的 `task.branch`（首用从 HEAD 创建），保证 merge 落在用户指定分支而非当前 checkout 分支。
- **防丢数据**：`_worktree_merge._auto_commit_dirty_worktree` 返回 worktree 是否干净；自动提交被拒（如 pre-commit hook）时 `merge_task_worktree` 返回 False 并**保留 worktree**，agent 未提交编辑绝不静默删除。
- **非法分支防御**：`_worktree_merge._is_valid_git_branch` 拒绝 `-` 开头/含 git 非法字符的 target 分支名（防 `git checkout` 选项注入），merge 跳过且保留 worktree 供人工处理。
- **cleanup 保数据**：`worktree_cleanup.cleanup_worktree` 默认 safe 模式——ARCHIVED/FAILED 清理前检测未提交改动，dirty 则保留 worktree 供人工恢复（merge 成功后的清理显式传 `force=True`）。唯一分支删除仅在 merge 成功之后。
- **merge 失败可观测**：merge 失败（冲突/不可提交/不可用分支）时 `move_orchestrator.merge_task_worktree` 追加 `MERGE_CONFLICT` 事件（payload 含 `conflicts` 文件列表），前端看板活动流可见。
