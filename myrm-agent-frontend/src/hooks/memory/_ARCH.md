# hooks/memory/

记忆域 API 的 React 状态封装：每个 hook 持有请求状态并转发对应 `@/services/memory/*` 客户端，不含 UI。当前没有组件消费这些 hook，`scripts/check-orphan-modules.mjs` 会列出它们。

| 文件                          | 职责                                                                                     |
| ----------------------------- | ---------------------------------------------------------------------------------------- |
| `useContextFabric.ts`         | 多源上下文实体抽取、项目实体关联与洞察沉淀（`services/memory/contextFabric`）            |
| `useDomainIsolation.ts`       | 连接器域绑定、域级权限（写入 / 召回 / 出口）与当前域上下文（`domainIsolation`）          |
| `useExperienceFlywheel.ts`    | 项目经验抽取、因果飞轮入库与雷区预嗅探（`experienceFlywheel`）                           |
| `usePersonCard.ts`            | 人物卡与关系画像的增删改合并、重力衰减刷新与行动前属性核验（`personCard`）               |
| `useProjectContextDongle.ts`  | 工作区四层 Markdown dongle 初始化、状态读取、提示词上下文与块同步（`projectDongle`）     |
| `useSafeEpisodicForget.ts`    | 情景记忆安全遗忘：先探测父级关联，再执行遗忘（`safeForget`）                             |
| `useSnapshotFreshness.ts`     | 会话记忆快照摘要、脏标记 / 过期跟踪与增量补丁注入（`snapshotFreshness`）                 |
| `useStalenessConsolidation.ts`| 记忆过期跟踪、召回刷新、仓库断言审计与合并提案（`stalenessConsolidation`）               |
| `useTranscriptProjection.ts`  | 会话投影冷启动与消息加载（`transcriptProjection`）                                       |
| `useVectorDimRebuild.ts`      | 向量集合维度检查与任务化重建（`vectorDimGuard`）                                         |
| `__tests__/use*.test.ts`      | 每个 hook 一份回归，与上表一一对应                                                       |
