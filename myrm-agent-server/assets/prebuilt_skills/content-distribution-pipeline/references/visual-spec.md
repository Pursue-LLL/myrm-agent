# Multi-Platform Visual Specifications & Aspect Ratio Standards

## Aspect Ratio Standards by Platform

| Platform | Primary Ratio | Dimensions (Recommended) | Format / Layout Role |
| :--- | :--- | :--- | :--- |
| **Xiaohongshu (小红书)** | **3:4** (Vertical Card) | 1080 × 1440 px | High-density information card / Bento-grid cover |
| **Douyin / TikTok (抖音短视频)** | **9:16** (Vertical Video) | 1080 × 1920 px | Full-screen video cover & B-roll backgrounds |
| **WeChat Official Account (微信公众号)** | **2.35:1** (Top Banner) | 900 × 383 px | Top header banner (首图) |
| **WeChat Official Account (微信公众号)** | **1:1** (Square Icon) | 500 × 500 px | Secondary list item thumbnail (次图) |
| **Twitter / X** | **16:9** (Landscape) | 1200 × 675 px | Summary card / Data chart header |
| **LinkedIn** | **1.91:1** (Landscape) | 1200 × 627 px | Professional thought-leadership header |

---

## Visual Design & Typographic Guidelines

1. **Information Density & Contrast**:
   - Ensure primary headlines occupy at least 30% of the visual focal area on mobile cards.
   - Use high-contrast color palettes (e.g. Navy Blue + Bright Yellow, Dark Charcoal + Coral Neon) to catch the eye in fast-scrolling feeds.
2. **Integration with `infographic` & Image Tools**:
   - When generating visual cards, leverage layout styles from `assets/prebuilt_skills/infographic/references/styles/`:
     * Xiaohongshu: `dense-modules` + `morandi-journal` or `craft-handmade`.
     * Douyin / Video: `bold-graphic` or `cyberpunk-neon`.
     * WeChat / Professional: `bento-grid` + `corporate-memphis` or `technical-schematic`.
3. **No Raw Emoji Clutter in Clean Assets**:
   - Keep design typography modern, clean, and brand-consistent.

---

## Standard Visual Asset Delivery Checklist

Every completed distribution bundle should contain `visual_assets/specs.md` detailing:
- [ ] Cover headline text and subtitle hierarchy.
- [ ] Aspect ratios generated (3:4, 9:16, 2.35:1).
- [ ] Prompt descriptions suitable for AI image generators (e.g. FLUX, DALL-E, Canvas).
- [ ] Color palette tokens and typography hierarchy.
