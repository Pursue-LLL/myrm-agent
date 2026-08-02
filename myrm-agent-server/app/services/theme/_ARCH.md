# theme/

Server-side theme services. Binary assets use FilesService; profile metadata lives in `personalSettings`.

## Submodules

| Module | Role | Doc |
|--------|------|-----|
| `package/` | `.myrmtheme` inspect / install / export | [_ARCH.md](package/_ARCH.md) |

## Dependencies

- `app/core/storage/files_service` — hero/poster asset storage
- `app/schemas/theme_profile.py` — ThemeProfileRecipe validation
- `myrm_agent_harness.backends.skills.scanning.zip_extract` — safe ZIP extraction

## API surface

- `app/api/theme/packages.py` — HTTP routes under `/theme/packages/*`
