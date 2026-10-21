# theme-packages/

REST clients for `.myrmtheme` import/export (server-authoritative inspect → install flow).

## Files

| File                     | Role                                                   |
| ------------------------ | ------------------------------------------------------ |
| `inspectThemePackage.ts` | `POST /theme/packages/inspect` multipart upload        |
| `installThemePackage.ts` | `POST /theme/packages/install` JSON body               |
| `exportThemePackage.ts`  | `POST /theme/packages/export` → Blob + download helper |

## Dependencies

- `@/lib/api` — `apiRequest`, `API_BASE_URL`
- `@/theme-engine/schema` — `ThemeProfileRecipe` type for install/export payloads

## Consumers

- `components/features/theme/AppearancePanel.tsx` — Import/Export buttons
- `components/features/theme/ThemePackageImportPreview.tsx` — inspect preview modal
