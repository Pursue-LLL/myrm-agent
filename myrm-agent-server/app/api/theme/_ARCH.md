# api/theme/

Profile metadata lives in `personalSettings` (validated by `app/schemas/theme_profile.py`); binary assets use FilesService.

## Files

| File | Role | I/O/P |
|------|------|-------|
| `router.py` | Aggregates theme routes under `/theme` | ✅ |
| `assets.py` | `POST /theme/assets/upload` — png/jpeg/webp/mp4 (80MB cap) | ✅ |
| `packages.py` | `POST /theme/packages/inspect|install|export|install-from-marketplace` — `.myrmtheme` ZIP | ✅ |

## Dependencies

- `app/core/storage/files_service` — unified file storage (Local / Sandbox)
- `app/services/theme/package/` — inspect whitelist, manifest, session store
- `myrm_agent_harness.backends.skills.scanning.zip_extract` — safe ZIP extraction
