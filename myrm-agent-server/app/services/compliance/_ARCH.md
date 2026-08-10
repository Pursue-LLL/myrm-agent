# compliance/

## Overview

Business-layer compliance scanning for WeChat Official Account HITL draft publish. Deterministic keyword scan before WeChat API calls; not an agent tool.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `wechat_compliance_scan.py` | Core | Title/digest/HTML visible-text scan (script/style/pre/code excluded), locale-aware reports, structured hits, high-risk block errors | ✅ |

## Dependencies

- Invoked by `app/channels/providers/wechat/draft_service.py` before draft upload
- 422 responses consumed by `ArtifactCard.tsx` WeChat draft panel

## Notes

- Scan runs on title, resolved auto/user digest, and visible HTML text (script/style/pre/code excluded).
- Auto digest uses the same visible-text SSOT as compliance scanning (pre/code omitted).
- High-risk categories block publish; medical-efficacy is warning-only.
- Non-blocking hits are returned in draft 200 `complianceWarnings` for ArtifactCard yellow panel.
