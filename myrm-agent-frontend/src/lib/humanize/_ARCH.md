# humanize — FE SSOT for tool presentation

## Purpose

Single frontend module that turns raw `tool_name` + args into human-readable one-liners for:

- ProgressSteps titles
- Approval card headlines (SingleApprovalCard, PolymorphicApprovalCard, ToolCallApproval)

## Public API (`index.ts`)

| Export                    | Role                                                  |
| ------------------------- | ----------------------------------------------------- |
| `humanizeProgressStep`    | Progress item title（`status=cancelled` → ask tense） |
| `humanizeApprovalTitle`   | Pending approval headline                             |
| `classifyApprovalSurface` | `compact` vs `full` approval layout                   |
| `resolveScopeNote`        | Plain-words scope hint (local / external / connector) |

## i18n

Namespace: `humanize.*` in all six locales (`en`, `zh`, `zh-TW`, `ja`, `ko`, `de`).

Subtrees: `progress`, `approval`, `ask`, `scope`, `fallback`.

## Wiring

| Consumer                      | Usage                                                        |
| ----------------------------- | ------------------------------------------------------------ |
| `progress-steps/utils.ts`     | `getStepTitle(..., tHumanize)` — humanize SSOT 唯一标题入口  |
| `SingleApprovalCard.tsx`      | title + scope note + compact payload hide                    |
| `PolymorphicApprovalCard.tsx` | subagent tool call headers + scope (`ApprovalScopeNoteLine`) |
| `ToolCallApproval.tsx`        | CLI agent approvals + scope + PTC badges                     |

## Boundaries

- FE-only; no harness/server/prompt changes.
- External scope matches channel tools in `EXTERNAL_TOOLS` only (not `target.includes(':')`).
- `#8 save_skill` preview UI：`SaveSkillApprovalPreview` + `saveSkillApproval.ts`；humanize 仅负责 headline/scope。
