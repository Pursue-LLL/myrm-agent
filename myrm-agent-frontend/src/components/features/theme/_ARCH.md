# theme/

Theme Engine v2 runtime: light/dark via next-themes + ThemeProfileProvider (Recipe compiler + Art Layer).

## Files

| File                                                 | Role                                                                                                                                                                                                                  | I/O/P |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `ThemeProvider.tsx`                                  | next-themes wrapper + theme-color meta                                                                                                                                                                                | ✅    |
| `ThemeProfileProvider.tsx`                           | ConfigSync profile → compiler → DOM + Art Layer + preinit; skips Art Layer and asset load on `/pet-overlay`                                                                                                           | ✅    |
| `ThemeAssetMissingBanner.tsx`                        | Non-blocking banner when synced `file:` assets are missing on this device                                                                                                                                             | ✅    |
| `WorkspaceArtLayer.tsx`                              | Full-window poster/video layer                                                                                                                                                                                        | ✅    |
| `restoreOfficialTheme.ts`                            | Execute official restore + draft/DOM preview cleanup                                                                                                                                                                  | ✅    |
| `AppearancePanel.tsx`                                | Profile picker + workspace background upload + wash + font + `.myrmtheme` import/export + restore official SSOT                                                                                                       | ✅    |
| `shared/SystemFontPicker.tsx`                        | Local Font Access API scan + developer font presets + custom typography picker                                                                                                                                        | ✅    |
| `shared/__tests__/SystemFontPicker.test.tsx`          | Unit tests for SystemFontPicker rendering, preset clicks, custom font submission, and reset                                                                                                                           | ✅    |
| `shared/ThemePackageImportSection.tsx`               | Shared `.myrmtheme` inspect/import/export + Desktop pending file; Zustand selector 用模块级空数组 fallback（禁止 selector 内 `?? []`）                                                                                | ✅    |
| `ThemePackageImportPreview.tsx`                      | Import preview modal (hero thumbnail, warnings, apply)                                                                                                                                                                | ✅    |
| `shared/ThemeMediaUploadField.tsx`                   | Hero file upload + client hero sampling (palette/layout hint); Theme Studio step 1 SSOT                                                                                                                               | ✅    |
| `shared/ThemePresetGrid.tsx`                         | Shared preset swatch grid (Appearance + Studio)                                                                                                                                                                       | ✅    |
| `shared/ThemeProfilePicker.tsx`                      | Built-in + saved profile picker (Appearance)                                                                                                                                                                          | ✅    |
| `theme-pre-init-script.ts`                           | Blocking tokens + pathname scene + functional opacity/wash floor + art poster preload + legacy purge（opacity 数值与 `scene-surfaces.FUNCTIONAL_SURFACE_FLOORS` parity 由 `__tests__/theme-init-asset.test.ts` 锁定） | ✅    |
| `__tests__/ThemeProfileProvider.petOverlay.test.tsx` | Regression: `/pet-overlay` skips `WorkspaceArtLayer` + missing-asset banner                                                                                                                                           | ✅    |
| `__tests__/restoreOfficialTheme.test.ts`             | Official restore executes ConfigSync patch + draft/preview cleanup                                                                                                                                                    | ✅    |

## Dependencies

- `@/theme-engine` — compiler + presets + overlay + preinit
- `@/services/theme-assets` — `uploadThemeBackground` SSOT + assetRef resolution + MP4 poster extraction
- `@/services/theme-packages` — `.myrmtheme` inspect / install / export API clients
- `@/lib/marketing-paths` — `isPetOverlayPath()` for art-layer skip on popped-out desk pet
- `PersonalSettings.activeThemeProfileId` / `themeProfiles` / `themeFontOverride` — ConfigSync SSOT
