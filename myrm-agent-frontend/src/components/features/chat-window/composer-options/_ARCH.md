# composer-options/

## 架构概述

桌面输入框的操作栏分两层：每条消息都会用到的 5 个控件常驻主行（`ComposerPrimaryControls`），其余选项收在「+」展开的选项区（`ComposerOptionsRegion`，分「思考 / 模式 / 能力」三组）。主行不再横向滚动，原先 14 个控件里有 11 个藏在横滑之后；手机（<`sm`）不显示这两块，由 `../composer/MobileComposerEntry` 的「+」打开 `../composer/MobileComposerSheet`。

选项区关着时不能让改变下一条消息的模式（编排、长期目标、深度搜索、无痕）无声地留在看不见的地方：「+」按钮上的小圆点、它的无障碍名称与悬停提示都会说出「已启用：…」（`useActiveComposerOptions`）。

## 文件清单

| 文件                                          | 地位 | 职责                                                                                                                                                                                                                                                                | I/O/P |
| --------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `ComposerPrimaryControls.tsx`                 | 核心 | 主行：「+」、Fast/Agent 切换、模型、权限档位、展开编辑器，一行不换行不滚动，只有模型名在窄屏下省略；`hidden sm:flex`，手机不渲染；第 6 个控件应放进选项区，由 `ComposerPrimaryControls.test.tsx` 与 `EmptyChat.contract.test.ts` 守卫                               | ✅    |
| `ComposerOptionsToggle.tsx`                   | 组件 | 「+」按钮：`aria-expanded` / `aria-controls` 指向选项区，展开时旋转为「×」；有模式开着时带圆点，名称与提示追加「已启用：…」；触屏上放大到 40px                                                                                                                      | ✅    |
| `ComposerOptionsRegion.tsx`                   | 核心 | 选项区（具名的 `section` 区域）：始终挂载，关着时 `inert`（移出 Tab 顺序与无障碍树，但控件状态与脚本点击照常），高度用 `grid-rows` 动画；三组带标题的行，控件全不渲染的整组连标题一起隐藏；分叉按钮仅在有会话、有消息且不在生成时出现；`hidden sm:grid`，手机不显示 | ✅    |
| `useComposerOptionsOpen.ts`                   | Hook | 选项区开合的本机记忆（键 `myrm.composer.optionsOpen`）：默认关；服务端与水合首帧都按「关」渲染，之后再套用已存的选择，不产生水合不一致；多个输入框与多个标签页同步                                                                                                  | ✅    |
| `useActiveComposerOptions.ts`                 | Hook | 「已启用：…」这句话的唯一出处：深度搜索只在 fast 模式下算、长期目标只在 agent 模式下算（另一模式遗留的值不播报）；顺序固定为深度搜索、编排、长期目标、无痕；按用户语言拼列表                                                                                        | ✅    |
| `__tests__/ComposerPrimaryControls.test.tsx`  | 测试 | 主行恰为 5 个控件且顺序固定、无滚动容器、手机不渲染；除模型名外的控件都不收缩（窄屏下权限档位不会折成两行）；「+」与编辑器按钮的接线与名称                                                                                                                          | ✅    |
| `__tests__/ComposerOptionsToggle.test.tsx`    | 测试 | 展开/收起名称与 `aria-*`、圆点与「已启用」名称、后开启的模式被拾取、点击只上报一次                                                                                                                                                                                  | ✅    |
| `__tests__/ComposerOptionsRegion.test.tsx`    | 测试 | 关着时 `inert` 但控件仍挂载、手机不显示、三组的成员与顺序、分叉按钮的出现条件与索引、能力选择器的属性透传                                                                                                                                                           | ✅    |
| `__tests__/useComposerOptionsOpen.test.tsx`   | 测试 | 默认关、存取与键名、跨实例与跨标签同步、水合首帧一致、存储拒绝写入时本页仍保持选择并在之后交还给存储                                                                                                                                                                | ✅    |
| `__tests__/useActiveComposerOptions.test.tsx` | 测试 | 各模式的计入条件、顺序、语言与随 store 更新                                                                                                                                                                                                                         | ✅    |

## 数据契约与依赖

- 选项区里的控件本身仍在 `message-input-actions/` 与同级目录（`ExpertSummonPopover`、`ForkButton`、`thinking-permission/`）；本目录只决定它们的分组与何时可达，不改它们的行为。
- 选项区内的弹层必须走 Radix 门户：区内为动画高度而 `overflow-hidden`，会裁掉定位在框外的内联浮层（`ComposerToolbar.popupPortal.contract.test.ts` 扫描本目录）。
- `../composer/useComposerPanels` 持有 `isTurnCapabilityOpen`（单轮能力弹层）：弹层锚在选项区内的控件上，所以它打开时选项区临时展开（`expanded = 已存选择 || 弹层开着`），不改写已存选择；再点「+」会同时关弹层与选项区。
- 开合记忆走 `@/hooks/ui/persistedStringStore`（与 `useProactiveDismissal` 共用的本机键值记忆）。
- 浮动输入框的高度随选项区变化，消息列末尾的 `ComposerClearanceSpacer` 据此保持最后一条消息不被遮住。
