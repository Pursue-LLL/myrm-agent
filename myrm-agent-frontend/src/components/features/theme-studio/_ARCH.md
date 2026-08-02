# theme-studio/

Theme Studio: four-step wizard to create full `ThemeProfileRecipe` entries, preview on Myrm shell mockups, apply/export `.myrmtheme`.

## Files

| Path | Role |
|------|------|
| `ThemeStudioSection.tsx` | Wizard orchestration, apply/export, live preview toggle |
| `gallery-listing-filter.ts` | Client-side Gallery search/sort helper |
| `ThemeStudioGalleryPanel.tsx` | CP Gallery Tab + gate + search/sort + Stripe 回跳 `theme_purchased` + record-install |
| `ThemeStudioCreatorPanel.tsx` | Creator submit + mine（CP gate；status i18n incl. pending/suspended / reviewReason） |
| `ThemeStudioAdminPanel.tsx` | Admin pending review + catalog suspend/restore（CP gate + admin API） |
| `ThemeMarketplaceGateBanner.tsx` | Offline / link-cloud CTA when CP unreachable or JWT missing |
| `hooks/useThemeMarketplaceGate.ts` | CP `/api/health` + JWT gate state |
| `ThemeStudioMarketplacePreviewDialog.tsx` | Install preview dialog for gallery |
| `ThemeStudioStepPanels.tsx` | Steps 1–4 panels; Step 3 includes preset grid + custom primary color picker (`derivePalette`) |
| `preview/ThemeStudioPreview.tsx` | Compiler-driven shell preview |
| `ProfileLibraryPanel.tsx` | List/edit/apply/delete `studio/*` and `imported/*` profiles |
| `RecipeImportPanel.tsx` | Paste Skill JSON into the wizard draft |
| `studio-profile.ts` | ID allocation + draft helpers |
| `hooks/useThemeStudioDomPreview.ts` | Workspace live preview via DOM compile only; zero ConfigSync writes |

## Boundaries

- Frontend-only; writes `personalSettings.themeProfiles` via ConfigSync.
- Reuses `#2` export API and theme asset upload services.
- AI generation via prebuilt skill `generate-myrm-theme` (server assets), not harness tools.

## Related

- Quick tweaks remain in `theme/AppearancePanel.tsx` (overlay fast path).
- Settings tab: `/settings/theme-studio`.
