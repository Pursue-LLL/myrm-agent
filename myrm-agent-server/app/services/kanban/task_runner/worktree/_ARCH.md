# services/kanban/task_runner/worktree/

KanbanTaskRunner 的 Git worktree 隔离子包——把任务代码与主仓库工作区隔离，任务完成后再安全 merge 回目标分支。由 `lifecycle.py` 编排分支唯一化与终态 merge、`merge.py` 处理 merge 前置 git 步骤、`cleanup.py` 负责 worktree 目录清理（safe 删除防丢数据）。聚合出口见 `worktree/__init__.py`。

[INPUT]
- task 对象（`task_id`/`branch`/`base_dir`）——分支唯一化与 merge 目标来源
- `app.core.utils.git_worktree`——共享 git 命令基础设施（add/remove/merge lock/identity 兜底）

[OUTPUT]
- `resolve_base_dir` / `resolve_workspace`——定位任务工作目录
- `create_worktree`——为任务创建独立 worktree 分支 `{target_branch}-{task_id[:8]}`
- `merge_task_worktree`——任务 COMPLETED 时 `--no-ff` merge 回目标分支，成功即清理目录与分支
- `cleanup_worktree`——safe/force 两档清理
- `worktree_dir` / `_sanitize_git_branch` / `_worktree_branch_name`——分支名消毒与唯一化（测试直接引用）

[POS]
Kanban worktree 隔离域。子包聚合出口职责：分支名消毒（`_sanitize_git_branch` 统一替换 git 非法字符）、唯一工作分支（`_worktree_branch_name` 防并行任务共享分支时 `git worktree add -B` 强制 reset 丢数据）、终态 merge 闭环（`merge_task_worktree` merge 后清理并删唯一分支，冲突时 `--abort` 恢复 repo 并保留 worktree 供人工处理）、merge 互斥（同 base_dir 由共享 `git_worktree._get_merge_lock` 串行化，防 "Unable to write index"）、git identity 兜底（未配置时注入 `-c user.name=Myrm Agent`）、防丢数据（dirty worktree 自动提交被拒时保留不删）。上级 SSOT：`../_ARCH.md`。
