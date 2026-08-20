# chat-window/goals/

Goal DAG control-plane UI inside chat window; state in `store/chat/goals/`.

| File                          | Responsibility                                                                                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `goalStatusTypes.ts`          | `GoalState` / `GoalStatus` / acceptance types (SSOT, re-exported by `GoalStatusCard`)                                                                               |
| `goalStatusUtils.ts`          | Pure helper functions: ETA computation, burn-rate/ETA formatting, reason translation, progress color                                                                |
| `GoalStatusCard.tsx`          | Active goal status card header + action buttons + pause dialog; delegates expanded view                                                                             |
| `GoalStatusExpanded.tsx`      | Expanded details: objective editor, step progress, token/burn-rate/ETA, constraints, acceptance criteria, deliverable bundle, subgoals, budget/human-review actions |
| `TaskDeliverableBundle.tsx`   | Aggregated deliverables card for completed Goals with 2+ artifacts; one-click ZIP download and per-file artifact preview                                            |
| `AcceptanceCriteriaPanel.tsx` | Acceptance criteria display with pass/fail badges and history                                                                                                       |
| `GoalControlPlane.tsx`        | Control-plane sidebar layout                                                                                                                                        |
| `GoalQueueSection.tsx`        | Queued goals list                                                                                                                                                   |
| `GoalPlanStepsList.tsx`       | Plan steps list (used in control-plane and mobile status)                                                                                                           |
| `useGoalPlanSync.ts`          | Plan ↔ store synchronization                                                                                                                                        |
| `goal-icons.tsx`              | Goal status SVG icons                                                                                                                                               |
