# services/projects/

项目长期事实账本与四层上下文投影的 API 客户端。项目本身的增删改与会话归属在同级 `../projects.ts`。

| 文件              | 职责                                                                                                                                                                  |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `projectState.ts` | 事实账本 DTO 与客户端：`recordLivingFact`、`listLivingFacts`、`getLivingFact`、`deleteLivingFact`，以及 `projectContext`（四层上下文投影）与 `auditValidation`（校验审计）；供 `components/features/memory/command-center/` 的事实账本、投影与校验面板使用 |
