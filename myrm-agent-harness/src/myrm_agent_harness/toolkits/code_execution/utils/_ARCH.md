# utils/

## Overview
Code execution utilities.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Code execution utilities. | — |
| log_distiller.py | Core | High-signal terminal log distiller for long-running build, execution, and deployment tasks (`DistilledLogResult`, `TerminalLogDistiller`) | ✅ |
| port_sniffer.py | Core | Dev-server listening-port sniffer for execution logs (`DiscoveredPort`, `sniff_ports_from_text`) | ✅ |
| scratch_dir.py | Core | The harness's own directories inside a workspace (`scratch_dir`, `ensure_scratch_dir`): `<workspace>/.myrm/<name>` for the command scripts (`exec`) and the output logs (`tee`). Each directory gets a `.gitignore` that holds `*`, so `git status` and `git add -A` never see what the harness keeps there and none of the user's own ignore rules is edited; an ignore file that cannot be written does not fail the caller, a directory that cannot be created does | ✅ |
| stderr_filter.py | Core | Fine-grained line-by-line stderr stream classification and filtering pipeline (`filter_stderr_text`, `classify_stderr_line`) | ✅ |
| workspace_path.py | Core | Workspace path resolver with intelligent auto-detection；当前运行绑定的工作区根（`workspace_root_var`）先于进程级缓存与环境探测，并发运行各自拿到自己的根；`/workspace` 别名按整段匹配（`/workspace2` 不是别名），定义在 `core/security/path/typed_path.py` 的 `container_relative`，`to_local_path` / `is_container_path` 与执行器 `resolve_path`、观察者、已保存脚本、权限引擎共用这一处 | ✅ |
