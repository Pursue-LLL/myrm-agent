# theme-engine/

Pure TypeScript Theme Engine v2: Recipe schema, layout surfaces, compiler, built-in presets, art overlay merge, pre-init snapshot helpers.

## Files

| Path | Role |
|------|------|
| `schema.ts` | ThemeProfileRecipe + layout/scene IDs |
| `layouts.ts` | Myrm-native layout surface opacity map |
| `layout-catalog.ts` | Studio layout cards + guidance i18n keys |
| `scene-surfaces.ts` | layout × scene merge + exported `FUNCTIONAL_SURFACE_FLOORS` / `FUNCTIONAL_ART_WASH_FLOOR` |
| `readability-scene.ts` | Route → immersive/functional scene SSOT |
| `compiler.ts` | Recipe → CSS vars + data attributes |
| `presets.ts` | 17 built-in ThemeProfile recipes |
| `oklch.ts` | WCAG contrast utilities + `derivePalette(hex)` |
| `recommend-layout-from-aspect.ts` | Hero aspect ratio → layout hint |
| `sample-hero-image.ts` | Client hero canvas sampling → palette hex + focal + layout hint |
| `overlay.ts` | Art overlay merge + background validation |
| `preinit.ts` | SSR/CSR zero-flash snapshot |
| `parse-recipe.ts` | Skill JSON → partial recipe |
| `official-restore.ts` | Official default restore SSOT |

## Boundaries

- Frontend-only pure TS; no React, no server I/O.
- Hero sampling (`sample-hero-image.ts`) runs in browser only; callers pass Blob (image or video poster).
- `ThemeProfileProvider` passes both layout + scene to `compileThemeProfile`; `data-myrm-theme-layout` no longer overridden by route.
