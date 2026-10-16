# services/kanban/task_runner/

KanbanTaskRunner 执行域。`runner.py` 为编排入口；`stream.py` 附件与 multimodal；`worktree/` Git 隔离子包（聚合出口见 `worktree/__init__.py`——`lifecycle.py` 分支唯一化 + 终态 merge 回目标分支 + per-base_dir merge 互斥；`merge.py` merge 前置 git 步骤（自动提交/可合并判断/target 分支切换/分支名校验）；`cleanup.py` worktree 目录清理（safe 删除防丢数据）；`landing_gate.py` 父任务合并失败时拦住依赖任务的运行入口）；`profile.py` agent profile 解析。worktree add/remove/分支删除/merge 组合等共享 git 命令基础设施复用 `app.core.utils.git_worktree`。上级 SSOT：`../_ARCH.md`。

## worktree 子包分支隔离设计

- **唯一工作分支**：每个任务创建独立 worktree 分支 `{target_branch}-{task_id[:8]}`（`_worktree_branch_name`），杜绝并行任务共享分支时的 `git worktree add -B` 强制 reset 数据丢失与隔离失效。
- **分支名消毒**：`_sanitize_git_branch` 统一替换 git 非法字符（空格/`~^:?*[\`/`..`/首尾 `-`），非法分支名不再静默 fallback 到错误目录。
- **终态 merge 闭环**：`merge_task_worktree` 在任务 COMPLETED 时（`move_orchestrator` 手动路径在后台执行并在合并落地后放行下游 + `dispatcher_lifecycle` task_completed 钩子）把唯一分支 `--no-ff` merge 回目标分支，成功后清理 worktree 目录并删除唯一分支；merge 冲突时收集冲突文件列表 → `git merge --abort` 恢复 repo（防 MERGE_HEAD 阻塞后续 merge）→ 保留 worktree 与分支供人工处理（绝不静默丢提交），返回 `(False, [冲突文件])`。
- **依赖任务等父任务的合并落地**：`resolve_workspace` 在解析工作区前调用 `worktree_landing.wait_parents_landed`——父任务的 merge 仍在后台进行时（派发器完成钩子与手动移到 COMPLETED 都经 `spawn_worktree_op(lands=…)` 登记），子任务先等它落地，worktree 才从含父任务产出的仓库切出；无分支的子任务直接在 base_dir 工作（merge 正写入的目录），同样等待。没有进行中的合并时不读库，不增加开销。
- **父任务合并失败时依赖任务不带病开工**：`runner.run` 的第一步是 `worktree.landing_gate.hold_for_unlanded_parents`——先等在途合并结束，再读父任务（同仓库、已完成、有分支）的事件流，有 `MERGE_CONFLICT` 事件（取最新一条）就说明它的代码没进分支，已完成的任务不能再次完成（`shared/config/kanban_move_guard.json` 只允许 `completed → archived`），这条记录不会被后来的完成覆盖；此时依赖任务若照常开工，会建在缺少该代码的仓库上，完成后又未经评审地自动合入分支。命中则返回 HUMAN 阻塞（`PARENT_MERGE_FAILED_REASON`，由 `dispatcher._handle_blocked` 落库，不计失败次数），在构造上下文与调用模型之前返回，所以不产生模型费用也不改变后续提示词。用户把任务解除阻塞即是确认：阻塞时 `metadata_patch` 已写入 `ACKNOWLEDGED_MERGE_FAILURE_KEY`（已见过的最新失败事件 id），同一失败不再拦第二次，之后更新的失败会再拦一次。
- **merge 互斥**：同一 base_dir 的 merge 由共享的 `git_worktree._get_merge_lock` 串行化（kanban 与 sandbox merge 同 repo 并发曾观测到 "Unable to write index"），不同仓库并行。
- **git identity 兜底**：auto-commit 与 merge commit 前经 `git_worktree._git_identity` 检测 repo 是否配置 user 身份，未配置时注入 `-c user.name=Myrm Agent -c user.email=agent@myrm.local`（不污染全局/仓库配置），bare repo 上自动合并不再失败。
- **显式 target 分支**：`worktree/merge._ensure_target_branch_checked_out` 在 merge 前把 base_dir 切换到任务声明的 `task.branch`（首用从 HEAD 创建），保证 merge 落在用户指定分支而非当前 checkout 分支。
- **防丢数据**：`git_worktree._auto_commit_dirty_worktree` 返回 worktree 是否干净；自动提交被拒（如 pre-commit hook）时 `merge_task_worktree` 返回 False 并**保留 worktree**，agent 未提交编辑绝不静默删除。
- **非法分支防御**：`worktree/merge._is_valid_git_branch` 拒绝 `-` 开头/含 git 非法字符的 target 分支名（防 `git checkout` 选项注入），merge 跳过且保留 worktree 供人工处理。
- **cleanup 保数据**：`worktree/cleanup.cleanup_worktree` 默认 safe 模式——ARCHIVED/FAILED 清理前检测未提交改动，dirty 则保留 worktree 供人工恢复（merge 成功后的清理显式传 `force=True`）。唯一分支删除仅在 merge 成功之后。
- **merge 失败可观测**：merge 失败（冲突/不可提交/不可用分支/抛错），或在排队时被关机取消而根本没有开始时，经 `worktree_ops.record_merge_failure` 追加 `MERGE_CONFLICT` 事件（payload 含 `conflicts` 文件列表），前端看板活动流可见。
