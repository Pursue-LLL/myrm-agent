# artifacts/

## Overview
Artifacts system — artifact lifecycle management.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Artifacts system — artifact lifecycle management. | — |
| constants.py | Core | Provides ArtifactType, ArtifactMappings, is_active_content. | ✅ |
| context.py | Core | Provides ArtifactContext, ArtifactContextManager, get_artifact_context. | ✅ |
| file_id_registry.py | Core | Numbers the files a run wrote with short `@file_NNN` ids (`register_file`, called by the file tools' artifact observer) and reports the id of a path (`lookup_short_file_id`) for the SSE `short_file_id`. A label for the UI only: the file tools and bash open the path they are given and never resolve an id, so the path the permission engine judged is the path that runs. | ✅ |
| filters.py | Core | File filtering rules for artifact collection. | ✅ |
| registry.py | Core | Provides GeneratedFile, ArtifactRegistry, RealtimeContentEvent. | ✅ |
| types.py | Config | Provides ArtifactInfo, infer_language, infer_artifact_type. | ✅ |
| bundle_manifest.py | Core | Provides DeliverableManifest, DeliverableItem, DeliverableCategory, DeliverableStatus for bundle packaging. | ✅ |
| vault.py | Core | Shared Artifact Vault — `vault://` store under `{workspace}/.agent/vault`（打开 vault 不碰磁盘，目录在第一次写入时才建；对象文件名是新生成的 UUID，写入不加文件锁，Windows 同样可用）; supports lifecycle purge (`purge_object`, `purge_objects`, `purge_by_task_id`, `purge_by_task_ids` — one vault scan for many task ids, `purge_all`), consumed by subagent auto-vault, file_read_tool, artifact listener, Kanban content_ref | ✅ |
