# market/

## Overview
Skill market module — search, install, update, and manage skills from external sources.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Skill market module. | — |
| autoupdate.py | Core | Skill auto-update checker. | ✅ |
| file_install.py | Core | `install_skill_files`: the in-memory install pipeline under a given install root (directory-name guard → lifecycle-script guard → quarantine write → security score gate → version guard → transactional promote with receipts, Agent Plugin sub-skill unpack); `is_safe_skill_dir_name`, `resolve_install_error`. | ✅ |
| file_uninstall.py | Core | `uninstall_skill`: removes a local skill under a given install root and cascade-removes the child skills a plugin installed (by `parent_plugin` / `skill_id` origin or receipt). The install-target safety check runs before any removal, so a rejected target keeps its child skills. | ✅ |
| helpers.py | Core | Skill market helper functions (write_origin with version, parent_plugin & declared_mcp_servers provenance, ranking, dedup). | ✅ |
| index_cache.py | Core | `SkillsIndexCache` — centralized static skills index cache with fast in-memory skill filtering. | ✅ |
| sanitizer.py | Core | Provides is_blocked_file, check_size_budget (the one size-limit decision: 1 MB per file, 5 MB in total; the git installer applies it before reading a file, `sanitize_skill_files` applies it at install), sanitize_skill_files. | ✅ |
| service.py | Core | Skill market service with deterministic multi-source merge, canonical archive-security mapping, dynamic source registration, Agent Plugins 1.0.0 multi-skill unpack & preview/install MCP transparency, version downgrade guardrail validation, and managed receipt generation. `install` and `install_from_url` run `sanitize_skill_files` inside the same `except ValueError` as the download, so a refused download or a size-limit failure comes back as a failed install with its reason. `install_files` is the public in-memory install entry, a thin delegate to `file_install.install_skill_files` with the service's install root, shared by market sources, LobeHub templates, and business-layer Agent Plugin skill imports. `uninstall` is likewise a thin delegate to `file_uninstall.uninstall_skill`. | ✅ |
| taps.py | Core | TapSubscription, TapDirectoryScanner, and GitHubTapSource for personal/enterprise private GitHub repo catalog synchronization. | ✅ |
| transaction.py | Core | Skill installation transaction and snapshot rollback manager with immutable receipt builder. | ✅ |

| Submodule | Description |
|-----------|-------------|
| installers/ | Skill installers. |
| sources/ | Skill data sources. |
| static_index/ | Static skills index engine and mirror cache. See [static_index/_ARCH.md](static_index/_ARCH.md). |

## Key Dependencies

- `backends`
