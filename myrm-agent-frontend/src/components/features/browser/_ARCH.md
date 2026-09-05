# Browser Features Module (Task Spaces)

浏览器并发子任务空间（Browser Task Spaces）前端交互模块。
提供多子任务并行浏览器的上帝视角悬浮感知 Dock 药丸、实时状态监视、人工接管切换（Takeover）与即时快照预览。

## Files

| File                               | Role | Description                                                                    | I/O/P |
| ---------------------------------- | ---- | ------------------------------------------------------------------------------ | ----- |
| `TaskSpaceDock.tsx`                | Core | 浮动胶囊 Dock 组件。支持展开收起、多空间状态指示、一键接管、快照预览及优雅关闭 | ✅    |
| `__tests__/TaskSpaceDock.test.tsx` | Test | 单元测试，覆盖空状态静默隐藏、展开收起、接管切换与关闭操作                     | ✅    |

## Dependencies

- `@/services/browserTaskSpaces` (POS: 浏览器任务空间 REST API 客户端与类型定义)
- `@/lib/utils/classnameUtils` (POS: Tailwind CSS 类名组合工具)
- `next-intl` (POS: 国际化多语言支持，对应 `taskSpaces` 命名空间)
- `lucide-react` (POS: 语义化轻量图标库)

## Integration Points

- `ChatWindowSatellites.tsx`: 在聊天工作台卫星层作为无侵入式浮动组件挂载，零干扰主聊天流
- `TaskSpaceDock.tsx`: 内置自适应空闲退避轮询机制（空闲且未展开时自适应降频至 10s 以上，活跃时保持 5s 探测），并通过 `safe-area-inset-bottom` 适配多端响应式与移动端安全边距
