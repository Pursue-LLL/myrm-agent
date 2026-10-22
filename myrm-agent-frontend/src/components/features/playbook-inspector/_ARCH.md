# playbook-inspector 架构自文档

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `playbookInspectorTypes.ts` | 类型契约 | 规约生命周期状态、失败追溯与行为规约实体定义 | ✅ 稳定 |
| `usePlaybookInspectorStore.ts` | 状态机 | 规约生命周期状态机、胜率更新、一键复活与置顶锁定仲裁操作 | ✅ 稳定 |
| `PlaybookRuleCard.tsx` | UI 组件 | 单条行为规约卡片，展示三态徽章、胜率进度条、失败会话追溯与复活操作 | ✅ 稳定 |
| `PlaybookLifecycleConsole.tsx` | 容器组件 | 判断力治理全景看板，多态过滤标签、实时关键词搜索与自定义规约创建模态 | ✅ 稳定 |
| `index.ts` | 模块入口 | 统一导出所有契约、Hook 与组件 | ✅ 稳定 |
