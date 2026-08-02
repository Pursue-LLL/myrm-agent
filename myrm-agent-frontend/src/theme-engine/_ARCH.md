# theme-engine/

Pure TypeScript Theme Engine v2: Recipe schema, layout surfaces, compiler, built-in presets, art overlay merge, pre-init snapshot helpers.

## Files

| File | Role |
|------|------|
| `schema.ts` | ThemeProfileRecipe / CompiledTheme types |
| `compiler.ts` | Recipe → CSS vars + Art Layer config + applyCompiledTheme |
| `layouts.ts` | Myrm-native layout surface opacity map |
| `layout-catalog.ts` | Studio layout cards + guidance i18n keys |
| `readability-scene.ts` | pathname → immersive/functional scene SSOT |
| `scene-surfaces.ts` | layout × scene merge + exported `FUNCTIONAL_SURFACE_FLOORS` / `FUNCTIONAL_ART_WASH_FLOOR` |
| `presets.ts` | 17 built-in profiles: default, 5 accents, 3 eye-care, 4 nature, 2 efficiency, 2 warm |
| `overlay.ts` | User art overlay merge + profile builders |
| `preinit.ts` | Blocking pre-hydration localStorage snapshot writer (tokens + optional art poster preload hint) |
| `oklch.ts` | WCAG contrast utilities + `derivePalette(hex)` + `resolveContrastSafeForeground` |
| `parse-recipe.ts` | Skill/clipboard JSON → validated ThemeProfileRecipe patch |
| `studio-constants.ts` | Ephemeral preview profile id + startup sanitize helpers |
| `index.ts` | Public exports |

## Boundaries

- Frontend-only runtime; no harness / no LLM token impact.
- Server stores profile metadata in `personalSettings`; media via `/api/theme/assets/upload` (`file:` refs).

## Readability scene (roadmap #8)

- **Layout** (`ThemeLayoutId`): user aesthetic choice persisted in Recipe.
- **Scene** (`ThemeReadabilityScene`): runtime route-derived — `immersive` (chat) vs `functional` (Kanban, Settings, …).
- `ThemeProfileProvider` passes both to `compileThemeProfile`; `data-myrm-theme-layout` no longer overridden by route.
- Cold start: `public/theme-init.js` resolves scene from `location.pathname` (keep aligned with `readability-scene.ts`).
- Functional opacity floors: exported from `scene-surfaces.ts`; parity asserted in `theme-init-asset.test.ts`.
- WCAG: `resolveContrastSafeForeground` sweeps achromatic lightness after brand neutrals; all `BUILTIN_THEME_PROFILES` asserted in `compiler.test.ts`.
