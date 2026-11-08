# decorators/

## Overview
SkillBackend decorator proxy — activated-version routing without mutating filesystem skill sources.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports decorator backends | — |
| version_aware.py | Core | VersionAwareSkillBackend — activated snapshot serving with filesystem fallback | baseline |

## Module Dependencies

- `backends.skills.protocols::SkillBackend`, `SnapshotStoreProtocol`
