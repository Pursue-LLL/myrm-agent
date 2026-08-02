# theme-engine/

Pure TypeScript Theme Engine v2: Recipe schema, layout surfaces, compiler, built-in presets, art overlay merge, pre-init snapshot helpers.

## Files

| File | Role |
|------|------|
| `schema.ts` | ThemeProfileRecipe / CompiledTheme types |
| `compiler.ts` | Recipe → CSS vars + Art Layer config + applyCompiledTheme |
| `layouts.ts` | Myrm-native layout surface opacity map |
| `layout-catalog.ts` | Studio layout cards + guidance i18n keys |
| `route-layout.ts` | pathname → work-dense auto switch |
| `presets.ts` | Built-in profiles (official-default + 6 accents + calm) |
| `overlay.ts` | User art overlay merge + profile builders |
| `preinit.ts` | Blocking pre-hydration localStorage snapshot writer (tokens + optional art poster preload hint) |
| `oklch.ts` | WCAG contrast utilities + `derivePalette(hex)` for custom primary color |
| `parse-recipe.ts` | Skill/clipboard JSON → validated ThemeProfileRecipe patch |
| `studio-constants.ts` | Ephemeral preview profile id + startup sanitize helpers |
| `index.ts` | Public exports |

## Boundaries

- Frontend-only runtime; no harness / no LLM token impact.
- Server stores profile metadata in `personalSettings`; media via `/api/theme/assets/upload` (`file:` refs).
