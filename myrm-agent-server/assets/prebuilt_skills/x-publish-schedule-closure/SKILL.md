---
name: x-publish-schedule-closure
description: >-
  Enterprise-grade publishing, thread slicing, and scheduled release workflow for X (Twitter)
  via the official xurl CLI. Enforces strict Human-in-the-Loop (HITL) pre-flight approval,
  character budget compliance (280 chars / CJK weighting), media attachment validation,
  and posts closure tracking with permanent status links.
version: 1.0.0
category: social-media
tags:
  - twitter
  - x
  - xurl
  - publishing
  - scheduling
  - hitl
  - thread-slicing
  - 社媒发布
  - 推特排期
  - 人机回环
allowed-tools: bash_code_execute_tool file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: Environment & Token Preflight — Check xurl CLI installation and OAuth2 authentication status without echoing tokens"
    - "Phase 2: Thread Slicing & Character Auditing — Validate copy against the 280-character limit with Chinese/CJK weighting, chunking into 1/N threads if necessary"
    - "Phase 3: Structured HITL Pre-Flight Gate — Present high-fidelity preview card (Content, Media, Scheduled Time, Account) and await explicit user sign-off"
    - "Phase 4: Execution & Status Closure — On confirmation, execute xurl post or schedule cron dispatch, returning tweet ID and permalinks"
  potential_traps:
    - description: "Autonomous publishing without explicit user confirmation"
      mitigation: "Strict prohibition: NEVER execute `xurl post` or live dispatch without explicit user [CONFIRM_POST] instruction"
      severity: critical
    - description: "Exposing OAuth bearer tokens, API keys, or ~/.xurl content into LLM context"
      mitigation: "Strictly forbid running cat ~/.xurl or using verbose flags (-v, --verbose)"
      severity: critical
    - description: "Tweet character limit overflow on multilingual or Chinese text"
      mitigation: "Audit character counts upfront (CJK characters count as 2 weight); slice into numbered threads (1/N) when length > 280"
      severity: high
  verification_steps:
    - step_id: zero_autonomous_dispatch_verified
      description: "Verify operational instructions strictly mandate explicit user sign-off before write actions"
      validation_method: "Inspect skill contract for mandatory HITL gate"
      is_required: true
    - step_id: thread_slicing_contract_defined
      description: "Ensure thread chunking conventions (1/N) and character budget rules are formally documented"
      validation_method: "Check character auditing section in skill markdown"
      is_required: true
  success_criteria: "A safe, audited X publishing and scheduling operation that never posts without human signoff and outputs permanent tweet verification links."
  estimated_duration_seconds: 180
---

# X (Twitter) Publish, Thread Slicing & Scheduling Closure Skill

## Overview

Publishing to X (Twitter) carries high public visibility. Autonomous agents posting unreviewed text or mishandling sensitive OAuth tokens can cause irreparable brand damage.

This skill provides an enterprise **Safety-Closed Publishing & Scheduling Pipeline** built on the official `xurl` CLI. It guarantees:
1. **Zero Autonomous Outbound Transmission** (Mandatory Human-in-the-Loop Signoff).
2. **Deterministic Thread Slicing & CJK Weight Auditing** (No broken tweets).
3. **Complete State Closure** (Captures Tweet ID, URL, and archives published state).

---

## 1. Operating Protocol

```text
Draft Input ──> CJK & 280-Char Budget Audit ──> Thread Slicing (1/N)
                                                     │
                                                     ▼
              Structured Pre-Flight Card <───────────┘
              (Text, Media, Target Slot)
                     │
                     ▼
             [HITL Human Signoff Gate]
              (Halt until user confirms)
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   [Instant Post]          [Scheduled Dispatch]
  xurl post ...          cron_manage_tool / at
        │                         │
        └────────────┬────────────┘
                     ▼
     Status Closure & Permalink Delivery
  (https://x.com/username/status/{id})
```

---

## 2. Character Budget & Thread Slicing Rules

- **Standard ASCII**: 1 character = 1 count (limit: 280).
- **Chinese / Japanese / Korean (CJK)**: 1 character = 2 counts (limit: 140 CJK characters).
- **Links (URLs)**: Count as 23 characters regardless of length.
- **Thread Slicing**: When length exceeds budget, slice logically into sequential replies:
  - Tweet 1: Hook + Core thesis `(1/3)`
  - Tweet 2: Supporting evidence & key takeaways `(2/3)`
  - Tweet 3: Summary + Call to Action (CTA) + Links `(3/3)`

---

## 3. Mandatory Pre-Flight Review Card Schema

Before calling any write command, the agent must output this review card and pause:

```markdown
### 🚀 X (Twitter) 发布前置审查卡片 (Pre-Flight Review Gate)

| 审核项 | 配置与详情 | 状态 |
| :--- | :--- | :--- |
| **目标账号** | `@company_official` (通过 xurl auth status 验证) | ✅ 校验通过 |
| **推文类型** | 单条推文 (Single Post) / 推文串 (Thread 3条) | 3 条串联 |
| **字数合规** | Tweet 1: 210/280 \| Tweet 2: 245/280 \| Tweet 3: 180/280 | ✅ 未超限 |
| **发布动作** | 立即发布 (Instant) / 定时排期 (2026-09-10 10:00 UTC+8) | 待用户确认 |

#### 📝 推文草稿内容预览:
> **[1/3]** 深度重构了 Agent 执行引擎后的第一手体会：把"幻觉式完工"在底层用物理证据门禁硬生生掐死，体验比靠 Prompt 哄模型听话好上 10 倍。以下是 3 个最致命的踩坑与自愈实践 👇
>
> **[2/3]** ...
>
> **[3/3]** 完整架构复盘已同步至开源仓库。欢迎试用与交流：https://github.com/...

---
⚠️ **发布门禁提示**：本技能严禁自主静默对外发推。请核对以上内容无误后回复 **`确认发布`** 或 **`确认排期`**，方可执行真实投递。
```

---

## 4. Execution & Closure SOP

Only after the operator explicit confirmation:

1. **Single Post**:
   ```bash
   xurl post '{"text": "Your verified post content here"}'
   ```
2. **Thread Posting**:
   - Post Tweet 1, parse response JSON to extract `id`.
   - Post Tweet 2 with `"reply": {"in_reply_to_tweet_id": "<id_1>"}`.
   - Continue sequentially until the thread completes.
3. **Delivery Closure**:
   - Output confirmation with direct permalink: `https://x.com/i/web/status/{id}`.
