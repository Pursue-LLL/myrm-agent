# GenUI 答案状态调和守卫套件架构设计 (_ARCH.md)

## 1. 业务愿景与核心痛点
在复杂 Agent 交互式生成 UI（GenUI）的审批与配置采集中（对应 dsh-genui PR #110 场景）：
- Agent 伴随多轮思考与动态推理，可能下发全新版本的表单描述文件（DynamicFormSpec）；
- 若前端无脑全量重置表单，用户已手动输入或调整的草稿值会被强制抹杀，造成灾难性录入损耗与阻断感；
- 核心设计原则：**User AnswersState (Dirty Fields) > Spec Defaults**。

## 2. 状态机与调和算法
```
                [ Agent 下发 Spec v2 / v3 ]
                           │
                           ▼
          ┌──────────────────────────────────┐
          │  reconcileAnswersWithSpec 守卫   │
          └────────────────┬─────────────────┘
                           │
      ┌────────────────────┴────────────────────┐
      ▼                                         ▼
[已脏字段 (isUserDirty)]                  [未修改/全新字段]
- 100% 保持用户当前输入                  - 增量合并 Spec 默认值
- 调和豁免，绝不覆盖                    - 自动同步最新演进配置
                           │
                           ▼
          ┌──────────────────────────────────┐
          │     更新 State & 触发调和通知    │
          │    (Preserved N, Initialized M)  │
          └──────────────────────────────────┘
```

## 3. 模块职责分工
- `genuiReconciliationTypes.ts`：纯类型定义（表单项 Spec、值类型、调和快照、Store 接口）；
- `reconciliationGuard.ts`：纯函数调和算法，无副作用，易于 100% 单元测试覆盖；
- `useGenUIAnswersReconciliationStore.ts`：基于 Zustand 的集中式响应式状态管理；
- `ReconciledDynamicFormCard.tsx`：支持多控件类型的高可访问性（a11y）渲染卡片，无原生 emoji，集成 Lucide 矢量图标。
