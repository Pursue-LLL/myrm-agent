# features/

## 架构概述

按产品域划分的客户端 UI：对话、设置、记忆、看板、技能等。页面 (`src/app/*`) 保持薄壳，主要逻辑在本目录子模块中。

## 子模块（目录）

| 目录                                          | 职责                                                                 | 文档                                                                              |
| --------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `app-shell/`                                  | 启动屏、认证/PWA 初始化器、全局对话框                                | [_ARCH.md](app-shell/_ARCH.md)                                                    |
| `chat-window/`                                | 主对话窗口、审批、Agent 配置、目标 DAG                               | [_ARCH.md](chat-window/_ARCH.md)                                                  |
| `message-box/`                                | 消息渲染与进度                                                       | [_ARCH.md](message-box/_ARCH.md)                                                  |
| `sidebar/`                                    | 会话侧栏                                                             | [_ARCH.md](sidebar/_ARCH.md)                                                      |
| `settings/`                                   | 设置页各 Section（含 Settings→通信→渠道 Provider 配置卡）            | [_ARCH.md](settings/_ARCH.md)                                                     |
| `memory/`                                     | 记忆中心                                                             | [_ARCH.md](memory/_ARCH.md)                                                       |
| `instance-archive/`                           | 整实例备份与恢复（导出、定时自动备份、导入向导、首次启动入口、撤销、重启提示、全局结果通知）                   | [_ARCH.md](instance-archive/_ARCH.md)                                             |
| `skills/`                                     | 技能管理、进化审核 Dashboard                                         | [_ARCH.md](skills/_ARCH.md)                                                       |
| `plugins/`                                    | Agent Plugins 1.0.0 导入向导 + 专家导出                              | [_ARCH.md](plugins/_ARCH.md)                                                      |
| `redaction/`                                  | 导出前脱敏复核（技能导出与专家导出共用）                             | [_ARCH.md](redaction/_ARCH.md)                                                    |
| `kanban/`                                     | 看板                                                                 | [_ARCH.md](kanban/_ARCH.md)                                                       |
| `projects/`                                   | 项目域仪表盘（Kanban/Cron/Artifacts 入口聚合）                       | [_ARCH.md](projects/_ARCH.md)                                                     |
| `project-workspace/`                          | Project 级同步目录绑定 UI（Mount Wizard）                            | [_ARCH.md](project-workspace/_ARCH.md)                                            |
| `health/`                                     | System Doctor                                                        | [_ARCH.md](health/_ARCH.md)                                                       |
| `onboarding/`                                 | 首次启动向导（迁移 + 本地能力 + Cookbook）                           | [_ARCH.md](onboarding/_ARCH.md)                                                   |
| `workspace/`                                  | 工作区与文件树                                                       | [_ARCH.md](workspace/_ARCH.md)                                                    |
| `cron/`                                       | 定时任务 UI                                                          | [_ARCH.md](cron/_ARCH.md)                                                         |
| `artifacts/`                                  | 工件与部署                                                           | [_ARCH.md](artifacts/_ARCH.md)                                                    |
| `companion/`                                  | 桌宠伴侣                                                             | [_ARCH.md](companion/_ARCH.md)                                                    |
| `copilot/`                                    | Lean Co-Pilot：Run Observer + Session Advisor（旁路只读问答）        | [_ARCH.md](copilot/_ARCH.md)                                                      |
| `e2ee/`                                       | E2EE 安全状态 badge + Popover 面板                                   | [_ARCH.md](e2ee/_ARCH.md)                                                         |
| `mobile/`                                     | Mobile Session Hub + 远程 HITL StatusBoard（`/mobile` 路由）         | [_ARCH.md](mobile/_ARCH.md)                                                       |
| `browser-inspector/`                          | 浏览器检查器                                                         | [_ARCH.md](browser-inspector/_ARCH.md)                                            |
| `desktop-inspector/`                          | 桌面检查器                                                           | [_ARCH.md](desktop-inspector/_ARCH.md)                                            |
| `image-editor/`                               | 图片标注编辑器（Canvas API）                                         | [_ARCH.md](image-editor/_ARCH.md)                                                 |
| `workspace-browser/`                          | 工作区内嵌文件浏览器与预览                                           | [_ARCH.md](workspace-browser/_ARCH.md)                                            |
| `background-tasks/`                           | 后台任务面板                                                         | [_ARCH.md](background-tasks/_ARCH.md)                                             |
| `browser-recording/`                          | 浏览器录制回放                                                       | [_ARCH.md](browser-recording/_ARCH.md)                                            |
| `files/`                                      | 文件展示层共享组件（文件类型图标）                                   | —                                                                                 |
| `checkpoint/`                                 | 会话检查点 UI                                                        | [_ARCH.md](checkpoint/_ARCH.md)                                                   |
| `eval-lab/`                                   | 评测实验室                                                           | [_ARCH.md](eval-lab/_ARCH.md)                                                     |
| `growth/`                                     | Growth 草稿与推广                                                    | [_ARCH.md](growth/_ARCH.md)                                                       |
| `icons/`                                      | 功能域专用图标（非 Lucide 通用集）                                   | [_ARCH.md](icons/_ARCH.md)                                                        |
| `image-gen/`                                  | 图片生成 UI                                                          | [_ARCH.md](image-gen/_ARCH.md)                                                    |
| `markdown-render-tools/`                      | Markdown 渲染扩展（Mermaid、代码块等）                               | [_ARCH.md](markdown-render-tools/_ARCH.md)                                        |
| `message-actions/` / `message-input-actions/` | 消息操作与输入区动作                                                 | [_ARCH.md](message-actions/_ARCH.md) · [_ARCH.md](message-input-actions/_ARCH.md) |
| `notifications/`                              | 通知中心                                                             | [_ARCH.md](notifications/_ARCH.md)                                                |
| `task-card/`                                  | 任务卡片组件                                                         | [_ARCH.md](task-card/_ARCH.md)                                                    |
| `theme/`                                      | Theme Engine v2（预设、壁纸、Compiler runtime）                      | [_ARCH.md](theme/_ARCH.md)                                                        |
| `theme-studio/`                               | Theme Studio：四步向导创建 ThemeProfileRecipe + 预览/导出 .myrmtheme | [_ARCH.md](theme-studio/_ARCH.md)                                                 |
| `voice/`                                      | 语音输入/会话 UI                                                     | [_ARCH.md](voice/_ARCH.md)                                                        |
| `file-preview/`                               | 通用文件预览                                                         | [_ARCH.md](file-preview/_ARCH.md)                                                 |
| `research/`                                   | Research 三栏研究工作台（资料池 + Chat + 工件输出）                  | [_ARCH.md](research/_ARCH.md)                                                     |
| `runs/`                                       | Unified Runs Hub 聚合运行历史                                        | [_ARCH.md](runs/_ARCH.md)                                                         |
| `loadout/`                                    | Agent Loadout 摘要 + Team Assets Hub（组合现有 API/面板）            | [_ARCH.md](loadout/_ARCH.md)                                                      |
| `embeds/`                                     | 外链 URL 富媒体嵌入（provider 匹配 + consent + iframe）              | [_ARCH.md](embeds/_ARCH.md)                                                       |
| `presentation/`                               | 演示文稿（PPT）生成弹窗、幻灯片渲染与预览下载                        | [_ARCH.md](presentation/_ARCH.md)                                |
| `task-inspector/`                             | 任务执行实时透视镜与技能调用时序可视化看板（步骤树、瀑布流、毫秒级耗时、插嘴打断） | [_ARCH.md](task-inspector/_ARCH.md)                                               |
| `reconnect-protocol/`                         | 基于单次原子状态快照与零事件重放 Live SSE 订阅的前后端无缝重连协议（极简状态胶囊、原子快照对齐与纯 Live 增量流） | [_ARCH.md](reconnect-protocol/_ARCH.md)                                           |
| `commands/`                                   | 情境感知型渐进式能力即时推荐、交互式快捷指令全景面板（“鼠标垫视图”）与智能微引导引擎 | [_ARCH.md](commands/_ARCH.md)                                                     |
| `canvas/`                                     | Canvas 画布文件严格沙箱隔离与交互式脚本动态鉴权体系（Strict CSP、iframe sandbox、出网审批门禁） | [_ARCH.md](canvas/_ARCH.md)                                                       |
| `quad-graph/`                                 | 四图分层动态拓扑视界与可观测图控制台（Task/Workflow/Team/Communication 四重视角切换、节点光晕点亮与实时 Steer 驾驶舱） | [_ARCH.md](quad-graph/_ARCH.md)                                                   |
| `roi-dashboard/`                              | 智能体可量化 ROI 生产力大盘与已节省时间价值看板（显性化工时大盘、投入产出比、任务分类贡献与高收益预置流程） | [_ARCH.md](roi-dashboard/_ARCH.md)                                               |
| `git-worktree/`                               | Git Worktree 侧边栏多工作区切换器、项目级会话聚合与历史 Checkout 自动锚定套件（分支下拉切换、会话锚定提示、文件触达视图） | [_ARCH.md](git-worktree/_ARCH.md)                                                 |
| `extension-widgets/`                          | 扩展小组件 ANSI 颜色渲染器与微型组件挂载宿主（Nano-Context 上下文占用表、Todo 任务清单） | [_ARCH.md](extension-widgets/_ARCH.md)                                           |
| `model-tester/`                               | 模型配置一键测速与连通性自检器（首字延迟 TTFT、TPS 吞吐量、呼吸状态健康徽标） | [_ARCH.md](model-tester/_ARCH.md)                                                 |
| `agent-assembler/`                           | “搭积木式”可视化智能体装配工作台与模块化能力编排器（六维积木卡片池、交互式拼装画布、即时微沙箱演练调试台） | [_ARCH.md](agent-assembler/_ARCH.md)                                             |
| `agent-avatar/`                              | 智能体头像生成工坊与 Dice 骰子锁定小部件（确定性 SVG 生成算法、4 种风格预设、骰子随机生图防误触锁定、AI 生图支持） | [_ARCH.md](agent-avatar/_ARCH.md)                                                 |
| `memory-hub/`                                | 智能体四大类记忆资产装备中心与细粒度 ACL 授权面板（Chat Memory/Skill/Wiki/CodeGraph 四类资产、4 槽位游戏化装备挂载与卸载、Private/Team/Project 三级 ACL 隔离） | [_ARCH.md](memory-hub/_ARCH.md)                                                   |
| `session-export/`                            | 全量会话交互式单文件 HTML 导出器与脱敏加密一键分享桥（零外部依赖 Standalone HTML、敏感凭据自动脱敏、折叠卡片与代码复制） | [_ARCH.md](session-export/_ARCH.md)                                               |
| `runtime/`                                  | 纯函数式多端状态投影中枢、实时运行时控制台与 Attempt 状态变迁透视抽屉（Quad-Surface 视图切换、Attempt 水位线与故障诊断） | [_ARCH.md](runtime/_ARCH.md)                                                     |
| `browser-annotation/`                       | 内置预览浏览器「点选圈批」与 DOM/CSS 元素精准批注系统（选区高亮、编号 Pin、DOM 特征提取、脱敏与子树分组并行修复） | [_ARCH.md](browser-annotation/_ARCH.md)                                           |
| `workspace-cockpit/`                        | 个人数字员工工作区总控驾驶舱（“你不在的时候”离线成果统计、4 泳道任务流、实时 streaming tail 与悬浮会话托盘） | [_ARCH.md](workspace-cockpit/_ARCH.md)                                             |
| `task-action-preview/`                      | 会话建议智能脱敏清洗转 Task（废话剥离、动宾行动项提炼）与高危操作 Typed Action 范围预览模态框及不可篡改操作回执卡 | [_ARCH.md](task-action-preview/_ARCH.md)                                           |
| `specialty-suites-gateway/`                 | 桌面端统一专业套件侧栏工作台与移动端免配置扫码热插拔伴侣网关（专家套件、企业连接器、统一定时中心、Ed25519 扫码配对） | [_ARCH.md](specialty-suites-gateway/_ARCH.md)                                       |

上表覆盖当前全部 feature 子目录。新增目录须同步本表并添加目录级 `_ARCH.md`。

## 依赖

- `@/components/primitives/*`
- `@/services/*`、`@/store/*`、`@/hooks/*`
