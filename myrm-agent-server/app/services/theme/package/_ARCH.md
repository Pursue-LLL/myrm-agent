# theme/package/

`.myrmtheme` ZIP contract: root whitelist, `recipe.json` manifest, inspect session store, install into FilesService-backed profiles, export with embedded binaries.

## Files

| File | Role | I/O/P |
|------|------|-------|
| `constants.py` | Size limits, schema version, session TTL | ✅ |
| `whitelist.py` | Root filename whitelist + MP4/APNG/animated WebP checks | ✅ |
| `manifest.py` | `recipe.json` Pydantic models + `to_installed_profile()` | ✅ |
| `session_store.py` | In-memory inspect sessions (TTL 30min) | ✅ |
| `inspect_service.py` | Safe extract + manifest validation + thumbnails (`signature_status=unsigned` for file uploads) | ✅ |
| `install_service.py` | Consume session → upload assets → profile | ✅ |
| `export_service.py` | Profile + `file:` refs → ZIP bytes | ✅ |
| `marketplace_signing.py` | Verify CP transport HMAC for marketplace downloads | ✅ |
| `marketplace_cp_client.py` | Sandbox → CP internal entitlement verify + record-install | ✅ |
| `marketplace_install_service.py` | Marketplace zip → inspect → install | ✅ |

## Dependencies

- `app/core/storage/files_service` — upload on install, read on export
- `myrm_agent_harness.backends.skills.scanning.zip_extract::safe_extract_zip` — archive security
- `app/schemas/theme_profile.py` — installed profile shape

## Constraints

- Package art refs are **relative filenames** pre-install; installed profiles use `file:` IDs.
- Installed profiles may carry optional `packageDescription` / `packageTagline` / `packageAuthor` for export fidelity.
- MP4 themes require poster image (`canImport=false` without it).
- Inspect holds unpacked bytes in memory until install or TTL expiry (single-user local server).
