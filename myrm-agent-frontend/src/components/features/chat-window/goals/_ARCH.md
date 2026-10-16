# chat-window/goals/

Goal DAG control-plane UI inside chat window; state in `store/chat/goals/`.

| File                          | Responsibility                                                                                                                                            |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `goalStatusTypes.ts`          | `GoalState` / `GoalStatus` / acceptance types (SSOT, re-exported by `GoalStatusCard`)                                                                     |
| `goalStatusUtils.ts`          | Pure helper functions: ETA computation, burn-rate/ETA formatting, reason translation, progress color                                                      |
| `GoalStatusCard.tsx`          | Active goal status card header + action buttons + pause dialog; delegates expanded view                                                                   |
| `GoalStatusExpanded.tsx`      | Expanded details: objective editor, step progress, token/burn-rate/ETA, constraints, acceptance criteria, deliverable bundle, budget/human-review actions |
| `GoalHumanReviewAction.tsx`   | Review-failed panel: reject-and-retry feedback (the goal goes back to work first, then the agent gets the message) or force approve                       |
| `GoalSubgoalsSection.tsx`     | Sub-goal list with add / remove: the input empties only once the server took the text (a held or failed sub-goal stays for editing), one add at a time    |
| `TaskDeliverableBundle.tsx`   | Aggregated deliverables card for completed Goals with 2+ artifacts; one-click ZIP download and per-file artifact preview                                  |
| `AcceptanceCriteriaPanel.tsx` | Acceptance criteria display with pass/fail badges and history                                                                                             |
| `GoalControlPlane.tsx`        | Control-plane sidebar layout                                                                                                                              |
| `GoalQueueSection.tsx`        | Queued goals list                                                                                                                                         |
| `GoalPlanStepsList.tsx`       | Plan steps list (used in control-plane and mobile status)                                                                                                 |
| `useGoalPlanSync.ts`          | Plan ↔ store synchronization                                                                                                                              |
| `goal-icons.tsx`              | Goal status SVG icons                                                                                                                                     |

目标文案或子目标被服务端风控拦下（HTTP 400 `risk_held`）时，`GoalStatusCard` 只展示 `services/riskHeldToast.ts` 的统一提示，不加「保存失败」类提示；其余失败各自提示。`GoalSubgoalsSection` 的子目标输入框只在服务端接收后清空（`onAddSubgoal` 返回是否被接收），被拦下或失败的文本留在框内可直接修改重发；请求未返回前的重复提交不会重复添加。

待人工复核的目标由 `GoalHumanReviewAction` 处理：驳回并重试先把反馈作为备注交给服务端，目标回到运行状态后才把同一段文字作为下一条消息发给智能体（智能体只读运行中的目标）；备注被风控拦下或请求失败时目标留在待复核、文字留在框内可修改重发；消息没被收下（服务端仍在忙、被拒或失败）时给出提示并把文字放回输入栏（栏内已有文字则不覆盖）；同一时刻只提交一次。`GoalStatusCard.handleAction` 返回服务端是否收下该操作，驳回备注不作为状态原因保存。该输入框与子目标输入框的 Enter 都先过输入法组合守卫（`isImeComposing`），候选词确认不会误提交。
