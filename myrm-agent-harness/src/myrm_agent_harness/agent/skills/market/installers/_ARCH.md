# installers/

## Overview
Skill installers.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Skill installers. | — |
| base.py | Core | Provides InstalledSkillFiles, SkillInstaller. | ✅ |
| git_installer.py | Core | Provides GitInstaller: shallow clone, then the skill directory from `subdirectory` (refused when it leaves the clone) and its files (hidden and junk directories are judged by the path segments below the skill directory only). | ✅ |
| zip_installer.py | Core | Provides ZipInstaller. | ✅ |
| batch_installer.py | Core | Provides HermesBatchParser for GUI bulk import. | ✅ |

## Key Dependencies

- `backends`
