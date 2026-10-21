---
name: generate-myrm-theme
description: >-
  Generate structured Myrm ThemeProfileRecipe JSON for Theme Studio and .myrmtheme
  packages. Use when the user wants an AI-generated workspace theme, hero image guidance,
  or a validated theme recipe. Never output raw CSS, JavaScript, or shell commands.
version: 1.0.0
category: design
tags:
  - theme
  - workspace
  - appearance
  - myrmtheme
allowed-tools: file_write_tool file_read_tool
contract:
  steps:
    - "Clarify mood, palette temperature, and whether the hero should be image or MP4-friendly still"
    - "Pick one Myrm layoutId: full-bleed | nav-rail-focus | chat-hero | work-dense"
    - "Emit a single ThemeProfileRecipe-compatible JSON object with relative asset filenames only"
  verification_steps:
    - step_id: recipe_schema_valid
      description: "Output JSON matches Myrm theme profile fields and uses relative asset refs"
      validation_method: output_contains_json_keys
---

# generate-myrm-theme

You help users create **Myrm workspace themes** for Theme Studio.

## Hard rules

- Output **one JSON object** matching Myrm `ThemeProfileRecipe` fields:
  - `name`, `layoutId`, `fontId`, `palette`, `art`
- `layoutId` must be one of: `full-bleed`, `nav-rail-focus`, `chat-hero`, `work-dense`
- `fontId` must be one of: `inter`, `system`, `atkinson`
- `art.mediaKind` is `image`, `video`, or `none`
- `art.assetRef` / `art.posterAssetRef` use **relative filenames** (e.g. `hero.png`), never `file:` URLs
- **Never** output CSS, JavaScript, HTML themes, or shell install steps
- Wrap JSON in a fenced code block labeled `json`

## Workflow

1. Ask what atmosphere the user wants (calm, energetic, professional, cinematic).
2. Recommend layout + wash + palette tokens that preserve readability on Kanban/Settings pages.
3. If generating an image, save via file tools and reference it as `hero.png` or `hero.mp4` in the recipe.
4. Provide optional `packageTagline` and `packageDescription` for export metadata.

## Example palette block

```json
{
  "primaryLight": "#588e95",
  "primaryDark": "#6ba3aa",
  "primaryHoverLight": "#4a7d84",
  "primaryHoverDark": "#7eb5bc",
  "primaryDarkLight": "#10505a",
  "primaryDarkDark": "#588e95",
  "dualAccent": true,
  "accentWarmLight": "#c96a28",
  "accentWarmDark": "#ffc47a"
}
```

After emitting the recipe, tell the user to paste it into Theme Studio or upload assets in step 1.
