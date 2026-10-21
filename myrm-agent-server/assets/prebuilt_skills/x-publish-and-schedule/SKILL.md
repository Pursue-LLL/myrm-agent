---
name: x-publish-and-schedule
description: >-
  Systematic, safety-gated automation skill for drafting, reviewing, scheduling, and publishing
  posts, threads, and media on X (formerly Twitter). Enforces strict Human-in-the-Loop (HITL)
  draft confirmation before submission, validates media aspect ratios, character limits,
  and provides scheduling calendar closure.
version: 1.0.0
category: social-media
tags:
  - x
  - twitter
  - social-media
  - publishing
  - schedule
  - marketing
  - 内容发布
  - 定时推文
  - 社媒运营
license: MIT
allowed-tools: browser_navigate_tool browser_snapshot_tool browser_interact_tool file_read_tool file_write_tool
contract:
  steps:
    - 1. Format and validate post copy against 280-character limit (or premium long-form)
    - 2. Verify attached media aspect ratios (16:9 for landscape, 1:1 for square, 4:5 for vertical)
    - 3. Present formatted preview card to the user for explicit confirmation (HITL Safety Gate)
    - 4. Access X web interface via browser automation or schedule draft via date/time picker
    - 5. Verify published tweet URL or scheduled status in X queue and record closure receipt
  potential_traps:
    - description: Publishing without explicit user confirmation of final copy and tags
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Silent truncation of tweets exceeding standard 280 unicode characters
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Account lockouts or bot challenges triggered by aggressive non-human browser interactions
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Misconfigured timezone leading to posts firing at incorrect scheduled hours
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
  verification_steps:
    - step_id: verify_1
      description: Ensure HITL confirmation was obtained before clicking final 'Post' or 'Schedule' button
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_2
      description: Verify post URL is accessible or scheduled entry appears in X Scheduled Posts drawer
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_3
      description: Confirm local receipt entry is written with timestamp, tweet copy, and status
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
  success_criteria: '100% human-approved post published or scheduled cleanly on X; Zero truncated copy or broken media attachments; Immutable audit receipt generated in workspace'
---

# X (Twitter) Publish & Schedule Closure Skill

This skill provides a dependable, safety-gated protocol for drafting, scheduling, and publishing single tweets,
multi-tweet threads, and media attachments on X without risking accidental unreviewed broadcasts or account suspension.

## Core Safety Pillars

1. **Mandatory Human-in-the-Loop (HITL) Review**:
   - **NEVER** click "Post" / "Tweet" automatically without first displaying the exact preview text and receiving affirmative user approval (e.g., "确认发布" or "Approve").
   - Any scheduled tweet must have its target date, time, and timezone explicitly acknowledged.

2. **Format & Constraint Validation**:
   - Standard Tweet length: ≤ 280 character units (CJK characters count as 2 units, URLs count as 23 units).
   - Thread sequence: Add numbered pagination (`1/n`, `2/n`) if drafting multi-tweet threads.
   - Media: Maximum 4 images per tweet or 1 video (MP4/MOV, ≤ 512MB).

3. **Stealth & Resilient Browser Automation**:
   - Utilize human-like typing delays (30ms - 80ms per keystroke).
   - Observe element stability after file uploads before navigating or clicking submit.
   - If a CAPTCHA or 2FA challenge is detected, immediately delegate to `browser_ask_human` for manual takeover.

## Standard Operating Procedure (SOP)

### Phase 1: Draft Formatting & Constraint Check
1. Prepare copy and sanitize markdown:
   - Convert markdown links `[text](url)` to plain URL format.
   - Ensure hashtags are relevant (recommend 1–3 maximum).
2. Measure character count using the X standard weighting formula.

### Phase 2: HITL Confirmation Gate
Present the draft preview to the user in the following standardized card:

```markdown
### 📢 X (Twitter) 发布草案预审 (HITL Review Gate)
- **发布类型**: [单推 / Thread 连推 / 定时推文]
- **计划发布时间**: [立即发布 / 2026-09-10 10:00 UTC+8]
- **字符长度**: [210 / 280]
- **媒体附件**: [无 / image_preview.png (16:9)]
---
**正文内容**:
> {Draft tweet text here}
---
⚠️ 请确认以上内容与排期。确认后将打开浏览器执行自动化提交流程。
```

### Phase 3: Browser Execution & Scheduling
1. Navigate to `https://x.com/compose/post`.
2. Locate the compose text area (`[data-testid="tweetTextarea_0"]`).
3. Fill text using `browser_interact_tool` (`fill` or `type`).
4. If scheduling:
   - Click the Schedule icon (`[data-testid="scheduleOption"]`).
   - Select target Month, Day, Year, Hour, and Minute.
   - Click "Confirm".
5. Submit post via `[data-testid="tweetButton"]`.

### Phase 4: Verification & Audit Receipt
1. Wait for toast notification (`Your post was sent` / `Your post was scheduled`).
2. Record receipt in `workspace/social/x_publish_log.jsonl`:
   ```json
   {"timestamp": "2026-09-10T02:40:00Z", "status": "scheduled", "text": "...", "target_time": "..."}
   ```
3. Return confirmation link or scheduled queue status to the user.
