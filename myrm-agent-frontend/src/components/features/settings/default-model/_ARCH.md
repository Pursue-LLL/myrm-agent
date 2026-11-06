# settings/default-model/

默认模型页的卡片与槽位组件：每张卡自行订阅自己的槽位，`sections/ai-core/DefaultModelSection.tsx` 只负责初始化/错误态、选择环境与卡片编排。

| 文件                                | 职责                                                                                                                          |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `modelSlots.ts`                     | 全部模型槽位（18 个）与 config 字段、store 写入动作的唯一绑定表；`useModelSlot` 读写单个槽位                                  |
| `ModelSelectRow.tsx`                | 绑定单个槽位的模型选择行（含「配置该模型」快捷入口）；`ModelSelectEnvProvider` 提供可选模型、provider、组织策略与模型详情弹窗 |
| `ModelCardParts.tsx`                | 卡片共用件：图标标题、预警条（`caution` / `missingFallback`）、备用模型卡                                                     |
| `BaseModelCard.tsx`                 | 主模型 + 备用；本地模型预警、无备用预警；内含视觉与视频备用卡                                                                 |
| `LiteModelCard.tsx`                 | 快速模型 + 备用；上下文窗口小于主模型预警（`isLiteWindowBelowBase`）                                                          |
| `BackgroundEvolutionCard.tsx`       | 后台自进化与维护模型 + 备用                                                                                                   |
| `SmartRoutingCard.tsx`              | 智能路由开关与轻量/推理/代码/长文档四个层级；`useFocusRoutingDeeplink` 处理 `?focus=routing` 高亮                             |
| `MediaFallbackCard.tsx`             | 视觉/视频备用卡的共用版式与按需健康探测（`useFallbackHealthCheck`）                                                           |
| `VisionFallbackCard.tsx`            | 视觉备用卡；主模型与备用都不能读图时给出一键推荐（应用后同步配置并探测）                                                      |
| `VideoFallbackCard.tsx`             | 视频备用卡                                                                                                                    |
| `useClearInvalidModelSelections.ts` | provider 配置加载后，一次性清除指向已不可用 provider/模型的选择（`isSelectionUsable`）                                        |
| `EnabledModelSelect.tsx`            | 启用模型选择；OpenCode Contributor 选中时展示 consent 提示                                                                    |
| `TemperatureSlider.tsx`             | 温度滑块                                                                                                                      |
