# processing/

## Overview
Post-fetch content processing: HTML to Markdown, pruning, sanitization, URL normalization, full-content delivery (one shared budget, complete text saved), anti-bot, binary routing.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports ContentPipeline | ✅ |
| pipeline.py | Core | ContentPipeline — HTML/JSON/XML to Markdown; a text response (`PayloadKind.TEXT`) becomes a Document verbatim. A Document built from a source the fetcher cut at its size ceiling (`FetchResult.source_truncated`) carries `SOURCE_TRUNCATED_KEY` in its metadata, whichever path built it; it is distinct from `was_truncated` (a cut to the caller's character budget) | ✅ |
| content_sanitize.py | Util | Strip base64 blobs from markdown | ✅ |
| content_pruning.py | Util | Boilerplate/noise pruning; a page nested beyond the scoring limit skips the scoring passes and keeps the structural cleanup | ✅ |
| html_to_markdown.py | Util | HTML to Markdown conversion; a table lists the rows of its nested tables itself, so nesting depth never multiplies the output | ✅ |
| markdown_table.py | Util | Markdown table layout of converted table rows: the header and delimiter lines span the widest row and body rows keep their own cells, so one wide row among many short ones never multiplies the output (blank header when the table has none) | ✅ |
| markdown_generator.py | Util | Markdown document generation | ✅ |
| url_normalizer.py | Util | URL normalization for dedup | ✅ |
| full_content_delivery.py | Core | Delivery plan for full-content reads: one shared character budget split max-min fairly across pages, a truncation window per cut page, the exact saved-file line range of every omitted section, newline-normalized and soft-wrapped saved text, failed-URL listing; pages are labelled with the numbers the caller gives (`indices`: the run's source numbers, so a label is the index of the page's card), from 1 when none; `source_notice` names, by those numbers only (so it may sit outside the untrusted boundary), the pages whose source the fetcher cut at its size ceiling | ✅ |
| spill.py | Util | Saves the complete text through the injected evicted-content callbacks, builds the read guide and announces the saved file to the GUI | ✅ |
| html_scan.py | Util | Linear-time scans of raw HTML text (title, body, script/style blocks, tags) for pages that may be hostile | ✅ |
| antibot_detector.py | Util | Anti-bot detection heuristics | ✅ |
| binary_router.py | Util | Binary content type routing (Content-Type, Content-Disposition, then `utils.content_sniff.magic_extension`); a payload no parser accepts is rejected, never decoded as text | ✅ |

## Dependencies

- `fetchers.protocols`, `utils.text_cleaner`, `utils.truncation_window`, `utils.context_format`, `core.security.detection.content_boundary`
