# services/theme-assets/

Theme media upload and assetRef URL resolution for Theme Engine Art Layer.

## Files

| File | Role | I/O/P |
|------|------|-------|
| `ThemeAssetStore.ts` | Resolve `file:` assetRef → URL; verify remote availability (HEAD/Range) | ✅ |
| `uploadThemeAsset.ts` | POST `/api/theme/assets/upload` client | ✅ |
| `extractVideoPoster.ts` | Client-side MP4 first-frame poster extraction before upload | ✅ |
| `__tests__/ThemeAssetStore.test.ts` | asset availability probe (HEAD + Range fallback) | ✅ |

## assetRef formats

| Prefix | Meaning |
|--------|---------|
| `file:<id>` | Server FilesService content URL |

Cloud uploads use `file:` refs from `POST /api/theme/assets/upload`. MP4 uploads also store a JPEG poster as `posterAssetRef`.
