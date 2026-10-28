# safe_git/

## Overview

Hardened `git` argv for the application's own, automatic git commands on a user- or agent-controlled working tree. A folder that arrives with its `.git` can name programs git runs during ordinary commands, and can aim a command at another repository's branches, index and files; every call the application starts itself goes through this package so neither happens outside the sandbox and approvals. The rules, measurements and consumers are described in the `safe_git/` row of [../_ARCH.md](../_ARCH.md).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Facade — re-exports `hardened_git_argv`, `hardened_git_argv_async`, `require_own_repository`, `HARDENED_GIT_CONFIG`, `HARDENED_GIT_ENV` and `GitHardeningError`; the import path of the single module it replaced is unchanged. | ✅ |
| argv.py | Core | The argv builder: fixed `-c` overrides, per-repository program neutralisation from one `git config --show-scope` listing, per-subcommand flags, and the order of checks for a command that touches the tree (layout verdict from files, configuration listing, then git's own answer where the files cannot decide). `require_own_repository` is the same verdict as a standalone check. | ✅ |
| layout.py | Core | Proof that the repository git would use for a directory is the directory's own: `lexical_layout` walks up exactly as git discovers a repository and classifies the first `.git` (own, foreign, absent, unknown) without a git process; `require_resolved_layout` settles the unknown and `core.worktree` cases with one `git rev-parse`. | ✅ |
| query.py | Core | `GitHardeningError` and `query_git`, the one read-only git query (5 s timeout) the configuration listing and the layout proof both use. Leaf module: imports nothing from its siblings. | ✅ |
