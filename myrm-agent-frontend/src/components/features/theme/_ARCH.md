# theme/

Theme Engine v2 runtime: light/dark via next-themes + ThemeProfileProvider (Recipe compiler + Art Layer).

## Files

| File | Role | I/O/P |
|------|------|-------|
| `ThemeProvider.tsx` | next-themes wrapper + theme-color meta | ✅ |
| `ThemeProfileProvider.tsx` | ConfigSync profile → compiler → DOM + Art Layer + preinit; honors Studio DOM preview | ✅ |
| `ThemeAssetMissingBanner.tsx` | Non-blocking banner when synced `file:` assets are missing on this device | ✅ |
| `WorkspaceArtLayer.tsx` | Full-window poster/video layer | ✅ |
| `AppearancePanel.tsx` | Profile picker + workspace background upload + wash + font + `.myrmtheme` import/export | ✅ |
| `ThemePackageImportPreview.tsx` | Import preview modal (hero thumbnail, warnings, apply) | ✅ |
| `shared/ThemePresetGrid.tsx` | Shared preset swatch grid (Appearance + Studio) | ✅ |
| `shared/ThemeProfilePicker.tsx` | Built-in + saved profile picker (Appearance) | ✅ |
| `theme-pre-init-script.ts` | Blocking tokens + pathname scene + functional opacity/wash floor + art poster preload + legacy purge | ✅ |

## Dependencies

- `@/theme-engine` — compiler + presets + overlay + preinit
- `@/services/theme-assets` — upload + assetRef resolution + MP4 poster extraction
- `@/services/theme-packages` — `.myrmtheme` inspect / install / export API clients
- `PersonalSettings.activeThemeProfileId` / `themeProfiles` / `themeFontOverride` — ConfigSync SSOT
