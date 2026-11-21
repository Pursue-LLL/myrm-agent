# humanize — FE SSOT for tool presentation

## Purpose

Single frontend module that turns raw `tool_name` + args into human-readable one-liners for:

- ProgressSteps titles
- Approval card headlines (SingleApprovalCard, PolymorphicApprovalCard)

## Public API (`index.ts`)

| Export                    | Role                                                                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `humanizeProgressStep`    | Progress item title（`status=cancelled` → ask tense）                                                                              |
| `humanizeApprovalTitle`   | Pending approval headline                                                                                                          |
| `humanizeToolLine`        | One-liner for a tool in `progress` / `approval` / `ask` tense (the two titles above wrap it; blocked-action rows call it directly) |
| `classifyApprovalSurface` | `compact` vs `full` approval layout                                                                                                |
| `resolveScopeNote`        | Plain-words scope hint (local / external / connector)                                                                              |

## i18n

Namespace: `humanize.*` in both locales (`en`, `zh`).

Subtrees: `progress`, `approval`, `ask`, `scope`, `fallback`.

A tool with no dedicated line reads `fallback.used_tool` ("Used …"); in `ask` tense, where the action never ran, it reads `ask.tool_generic` ("Wanted to use …") instead, and a locale without that key keeps the past-tense line.

## Wiring

| Consumer                                  | Usage                                                            |
| ----------------------------------------- | ---------------------------------------------------------------- |
| `progress-steps/utils.ts`                 | `getStepTitle(..., tHumanize)` — humanize SSOT 唯一标题入口      |
| `ApprovalDetails.tsx`                     | title + scope note                                               |
| `SingleApprovalCard.tsx`                  | compact payload hide                                             |
| `PolymorphicApprovalCard.tsx`             | subagent tool call headers + scope (`ApprovalScopeNoteLine`)     |
| `features/cron/CronRunBlockedActions.tsx` | rows of the actions a run's safety rules stopped, in `ask` tense |

## Boundaries

- FE-only; no harness/server/prompt changes.
- External scope is exactly the tools in `EXTERNAL_TOOLS` (`channel_notify_tool`, `artifact_publish`): the tools of the backend's
  socially irreversible set (`_IRREVERSIBLE_SOCIAL_TOOLS`, harness `core/security/spend_governance.py`) that exist. Keep the two lists in step.
  `channel_notify_tool` names its `destination` parameter as given in the scope note and the approval title; `artifact_publish`
  reads `scope.external_unknown` because its hosting target is an id nobody can read. A colon in a `target` never makes a call external.
- `#8 save_skill` preview UI：`SaveSkillApprovalPreview` + `saveSkillApproval.ts`；humanize 仅负责 headline/scope。
