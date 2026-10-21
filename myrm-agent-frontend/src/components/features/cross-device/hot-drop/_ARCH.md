# Cross-Device Hot-Drop & Wireless Camera Beam Architecture (`cross-device/hot-drop`)

## 1. 架构定位与业务痛点
针对传统办公场景下“手机拍白板/票据传给电脑端 AI 必须依赖微信文件传输助手或网盘中转”的繁重割裂链路，以及厂商私有碰一碰硬件协议的生态孤岛，本模块构建跨 iOS/Android/Mac/Windows 全平台通用的“近场零摩擦热直投通道”与“手机瞬态外设无线相机枪”。

## 2. 模块拓扑与职责划分
- **`crossDeviceDropTypes.ts`**：定义设备配对状态机（`idle` | `pairing` | `connected` | `beaming` | `completed` | `error`）、直投载荷 `BeamPayload`、会话描述符与光标热注入结果；
- **`beamTransportProtocol.ts`**：纯函数协议引擎，支持 6 位易读配对短码生成、频道生成、多格式（JPG/PNG/WebP/HEIC/PDF）合规校验与文件尺寸计算；
- **`useCrossDeviceDropStore.ts`**：Zustand 集中式状态管理，控制近场直投会话生命周期、待注入素材队列，并向宿主输入框广播 `myrm:hot-drop-received` 与 `myrm:hot-drop-injected` 全局事件；
- **`DesktopBeamAnchorButton.tsx`**：桌面端输入框附件栏常驻微型直投锚点，悬浮展示动态扫码卡片、PIN 短码、连接呼吸灯与局域网直连状态；
- **`MobileCameraBeamView.tsx`**：手机端轻量外设相机枪界面，支持拉起系统原生相机与相册选图，一键 1 秒直投电脑输入框；
- **`HotDropPayloadInjector.tsx`**：桌面端素材到达后的即时悬浮挂载卡片，支持 OCR 预览、附带提示词查看与一键注入当前光标焦点处。

## 3. 极不友好 Code Review 12 项清单遵循度
1. **零 Any**：全链路强类型契约；
2. **零原生 Emoji**：全部采用 Lucide 矢量图标（`Smartphone`, `Camera`, `Zap`, `CheckCircle2` 等）；
3. **前端所有 If 显式带大括号**：严格杜绝简写单行语法；
4. **单文件行数严格受控**：各文件代码行数严格控制在 240 行以内（远低于 400 行红线）；
5. **a11y 无障碍标准**：符合语义化标签、聚焦管理与键盘操作（Escape 取消，Enter 确认）。
