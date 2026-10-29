# installers/

## Overview
Skill installers.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Skill installers. | — |
| base.py | Core | Provides InstalledSkillFiles, SkillInstaller. | ✅ |
| git_installer.py | Core | Provides GitInstaller: shallow clone, then the skill directory from `subdirectory` (`safe_join_path`; refused when it leaves the clone) and its files. The clone is untrusted input: a symlink is followed only when its real target is inside the clone (a link leaving it is skipped with a warning; a symlinked directory is never entered by the file walk), hidden and junk directories are judged by the names below the skill directory only and are never entered, paths the install step filters are skipped, and a file over the single-file limit or a skill over the total limit (`sanitizer.check_size_budget`, the decision `sanitize_skill_files` applies at install) is refused before its bytes are read. Directory scans, reads and the cleanup of the clone run in a worker thread. | ✅ |
| zip_installer.py | Core | Provides ZipInstaller. | ✅ |
| batch_installer.py | Core | Provides HermesBatchParser for GUI bulk import. | ✅ |

## Key Dependencies

- `backends`
- `core.security.path` — `safe_join_path`, `is_within_boundary` (real-path containment of the clone)
- `agent.skills.market.sanitizer` — `is_blocked_file`, `check_size_budget` (the file filter and size limits of the install step)
