---
name: x-publish-schedule
description: >-
  Compose, validate, schedule, and safely publish content to X (Twitter) with mandatory Human-In-The-Loop (HITL) approval,
  character & media compliance gates, thread auto-segmentation, and schedule verification readbacks.
version: 1.0.0
category: social-media
tags:
  - x-publish
  - twitter
  - content-scheduling
  - hitl-gate
  - social-media
  - thread-builder
allowed-tools: file_read_tool file_write_tool memory_save_tool memory_search_tool
contract:
  steps:
    - "Phase 1: Content Composition & Format Validation — draft tweet or thread copy, calculate 280-weighted characters (CJK=2, ASCII=1, URL=23), check media constraints"
    - "Phase 2: Sensitive Data & Compliance Screening — verify no private keys, passwords, API tokens, internal URLs, or defamatory claims exist in copy or images"
    - "Phase 3: Human-In-The-Loop Confirmation Gate — present structured Pre-Publish Approval Card with target handle, copy preview, and schedule timestamp; require explicit confirmation"
    - "Phase 4: Execution & Schedule Verification Readback — emit idempotent dispatch payload, record publication receipt with verification hash and audit log"
  potential_traps:
    - description: "Auto-publishing or scheduling without explicit human confirmation, risking PR blunders or unreviewed content"
      mitigation: "Strictly block publishing operations until the user provides an unequivocal 'Confirm Publish' or 'Confirm Schedule' response"
      severity: critical
    - description: "Character count overflow causing silent post truncation on platform"
      mitigation: "Enforce precise X weighted character count algorithm: ASCII=1, CJK=2, URL=23, Emoji=2; auto-split into numbered threads when exceeding 280 characters"
      severity: high
    - description: "Timezone misinterpretation leading to scheduled posts firing at unintended hours"
      mitigation: "Explicitly display both local user time and UTC ISO-8601 timestamp in the confirmation card and require scheduled time to be >= 10 minutes in the future"
      severity: high
    - description: "Accidental credential or confidential data leak inside code blocks or screenshot attachments"
      mitigation: "Automated pre-flight regex scan for API tokens, secret keys, bearer headers, and staging domain names before approval card generation"
      severity: critical
  verification_steps:
    - step_id: hitl_explicit_approval_received
      description: "Ensure explicit user approval is registered before triggering any write/publish action"
      validation_method: "Verify user prompt explicitly confirms publication or scheduling"
      is_required: true
    - step_id: character_and_media_compliance_passed
      description: "Ensure character length <= 280 (or formatted as valid thread) and media adheres to image/video guidelines"
      validation_method: "Inspect weighted char counts and verify media count <= 4 images or 1 video"
      is_required: true
    - step_id: schedule_future_timestamp_validated
      description: "Ensure scheduled publishing time is strictly valid and in the future"
      validation_method: "Check timestamp > current_time + 10min and format matches ISO-8601"
      is_required: true
    - step_id: audit_receipt_generated
      description: "Produce deterministic audit log and publication receipt"
      validation_method: "Verify task receipt contains account handle, post hash, and status"
      is_required: true
  success_criteria: "A completely validated, brand-safe, compliance-verified X post or thread ready for immediate dispatch or scheduled execution with an immutable audit receipt."
  estimated_duration_seconds: 400
---

# X (Twitter) Publish & Schedule Closure Skill Pack (X 自动化排期与发布确认安全闭环)

## Overview

The `x-publish-schedule` skill provides a production-grade, safe, and verifiable write path for X (Twitter). It guarantees that agents never blindly post unreviewed content, leak secrets, or botch formatting. By pairing rigorous pre-flight validation with a mandatory **Human-In-The-Loop (HITL) Safety Gate**, marketing teams, founders, and community managers can automate content drafting, thread assembly, and publishing schedules with 100% confidence and auditability.

---

## 1. X Native Format & Weighted Length Rules

All outbound copy must strictly conform to X's native text and media rules:

### A. Weighted Character Calculation
| Element Type | Weight Rule | Example & Notes |
|---|---|---|
| **ASCII / Latin Characters** | 1 unit per character | `A-Z`, `a-z`, `0-9`, spaces, ASCII punctuation |
| **CJK Characters (中文 / 日文 / 韩文)** | 2 units per character | 每个中文字符、全角标点均计 2 字符 |
| **HTTP / HTTPS URLs** | Fixed 23 units | Any link (regardless of actual URL length) is normalized to `t.co` (23 chars) |
| **Standard Emojis** | 2 units per glyph | `🚀`, `💡`, `✨` (treat ZWJ sequences carefully) |
| **User Mentions (`@handle`)** | Length of handle + 1 | e.g. `@openperplexity` = 16 units |

- **Single Tweet Ceiling**: Max **280 weighted characters**.
- **Thread Threshold**: If weighted characters exceed 280, automatically convert copy into a multi-part Thread (`1/N`, `2/N`, ... `N/N`).

### B. Media Attachment Constraints
- **Images**: Maximum **4 images** per tweet. Supported formats: JPG, PNG, WEBP, GIF. Max file size: 5MB per image.
- **Videos**: Maximum **1 video** per tweet. Supported formats: MP4, MOV. Max file size: 512MB. Max duration: 140 seconds (for standard accounts).
- **Mutual Exclusivity**: A tweet cannot contain both images and videos simultaneously.

---

## 2. Mandatory Human-In-The-Loop (HITL) Safety Gate

> ⚠️ **Absolute Safety Invariant**: Under NO circumstances should an agent trigger live publication or final scheduling without rendering the Pre-Publish Approval Card and receiving explicit user confirmation.

### Pre-Publish Approval Card Template

Before requesting execution, format and present the following audit block to the user:

```markdown
### 📋 X (Twitter) 发布核准单 (Pre-Publish Approval Card)

- **目标账号 (Account)**: `@{account_handle}`
- **发布类型 (Type)**: `[单推 Single | 串推 Thread (共 N 条) | 定时排期 Scheduled]`
- **预定发布时间 (Schedule Time)**: `{YYYY-MM-DD HH:mm:ss (本地时区) / ISO-8601 (UTC)}`
- **推文正文 (Content Preview)**:
  > {tweet_text_or_thread_preview}
- **字符统计 (Weighted Length)**: `{actual_length} / 280` {length_status_badge}
- **附件媒体 (Media Attachments)**: `{media_list_or_none}`
- **安全扫描 (Safety & Leak Scan)**:
  - 凭据密钥扫描: `[通过 PASS - 无泄漏]`
  - 链接安全性: `[通过 PASS - 无死链或违规域名]`
  - 语气与合规: `[符合品牌调性]`

---
👉 **请确认：回复「确认发布」或「确认排期」执行，或提出修改意见。未经明确授权本流程保持锁定。**
```

---

## 3. Thread Auto-Segmentation SOP

When content length exceeds 280 weighted characters, follow this deterministic thread structuring procedure:

```
[Main Tweet 1/N]
  ├── Strong Hook (First 30 characters must capture attention)
  ├── Core Thesis / Key Insight
  └── Reading roadmap indicator (e.g., "A thread on how we achieved X ↓")
       ↓
[Body Tweets 2/N to N-1/N]
  ├── One atomic sub-point or evidence chunk per tweet
  ├── Accompanying screenshot, diagram, or code snippet
  └── Natural logical transition to the next tweet
       ↓
[Closing Tweet N/N]
  ├── Executive Summary / Key Takeaways
  ├── Call To Action (RT the first tweet, bookmark, link to repository/post)
  └── Attribution / Disclaimers
```

---

## 4. Scheduling Verification & Idempotency Readback

For scheduled posts:
1. **Timestamp Guard**: Scheduled time must be at least **10 minutes** ahead of current system time and at most **180 days** in the future.
2. **Idempotency Key Generation**: Generate a deterministic hash for deduplication:
   `hash = sha256(account_handle + scheduled_timestamp_utc + tweet_body)`
3. **Receipt Generation**: Upon receiving user confirmation, output an audit receipt:

```json
{
  "receipt_id": "x_pub_rec_20260910_a1b2c3d4",
  "account_handle": "myrm_ai",
  "publish_mode": "scheduled",
  "scheduled_at_utc": "2026-09-10T14:30:00Z",
  "status": "QUEUED_AND_LOCKED",
  "idempotency_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "verified_by_user": true
}
```
