---
name: wechat-article-formatter
description: >-
  Convert Markdown articles into WeChat Official Account styled HTML with inline CSS,
  code highlighting blocks, and local image path preservation for draft publishing.
version: 1.0.0
category: content
tags:
  - wechat
  - markdown
  - html
  - content
  - publishing
allowed-tools: bash_code_execute_tool file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: Read the source Markdown from the workspace vault path"
    - "Phase 2: Run md_to_wechat_html.py to produce styled HTML beside the source file"
    - "Phase 3: Confirm output exists; user previews HTML artifact and pushes to draft via WebUI"
  success_criteria: "Non-empty .wechat.html file with WeChat-friendly inline CSS"
  estimated_duration_seconds: 300
---

# WeChat Article Formatter

Convert workspace Markdown into WeChat Official Account HTML. The output is meant for **preview in WebUI** and **manual push to the WeChat draft box** (HITL).

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Workflow

1. **Read** the user's Markdown file with `file_read_tool`.
2. **Convert** using the bundled script (do not hand-write HTML):

```bash
python assets/prebuilt_skills/wechat-article-formatter/scripts/md_to_wechat_html.py \
  /path/to/article.md \
  -o /path/to/article.wechat.html
```

If the skill assets path differs in the sandbox, locate the script under `assets/prebuilt_skills/wechat-article-formatter/scripts/`.

3. **Verify** the HTML file exists and is non-empty.
4. Tell the user to preview the HTML artifact and click **Push to WeChat Draft** when ready.

## Rules

- Preserve relative image paths in Markdown (`![](./images/foo.png)`); the draft API uploads them to WeChat CDN.
- Do **not** auto-publish to WeChat; publishing requires explicit user confirmation in the UI.
- For cover image: ensure at least one local image in the article, or the user must provide a cover when pushing the draft.
- Requires **WeChat Official Account** credentials (AppID/AppSecret) configured in Settings.

## Output quality

- Headings use green accent styling suitable for 公众号 readers.
- Code blocks use Pygments via `codehilite` with inline token colors (`noclasses`) for WeChat draft compatibility; preview CSS stays in `<head><style>`.
- Keep the source `.md` as SSOT; HTML is a derived artifact only.
