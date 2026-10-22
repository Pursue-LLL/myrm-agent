# Web AudioWorklet Duplex Voice Stream & Autoplay Resilience Suite 架构说明

## 1. 业务目标与核心价值
彻底破除桌面端 Agent 迁移到 Web 端时因浏览器沙箱机制导致麦克风权限缺失、音频 Autoplay 策略拦截报错以及高延迟卡顿的核心能力断裂硬伤。
对标 Hermes PR #93508 官方核心维护者 @Teknium 与音频架构专家 @Kyssta 深度论证，实现：
1. **安全上下文环境探针 (Secure Context Detector)**：高精度识别页面运行环境是否具备调用 getUserMedia 与 WebCrypto 的安全凭据，特别针对局域网 HTTP 直连（如 192.168.x.x / 10.x.x.x）提供即时能力降级警示与 Tailscale TLS 域名迁移自愈指引；
2. **Autoplay 策略弹性防御 (Autoplay Policy Resilience)**：监听并探测 AudioContext 的 `suspended` 挂起状态，通过用户显式手势交互优雅解除静默拦截，杜绝 `NotAllowedError` 报错；
3. **AudioWorklet 独立采样与轻量 VAD (PCM Sampling & VAD)**：在独立音频上下文中完成 16kHz PCM 单声道重采样与 RMS 分贝能量测算，利用前端状态机精准捕捉用户说话（Speech）与静音（Silence）断句，避免主 UI 线程卡顿引起的爆音丢帧；
4. **全双工实时交互控制卡片 (VoiceStreamControllerCard)**：工业级可视化音频波形、分贝仪表、实时 RTT 延迟与环境诊断自愈看板。

## 2. 核心架构设计
- `voiceStreamTypes.ts`: 纯粹强类型系统，零 `any`，严格规范全双工状态、PCM 帧结构、VAD 状态机与安全报告；
- `secureAudioContextDetector.ts`: 纯逻辑环境探针与 Autoplay 手势解锁引擎，物理识别 Localhost、HTTPS、局域网 HTTP 降级与 getUserMedia 接口就绪度；
- `audioPcmProcessor.ts`: 纯函数 PCM 采样转换（Float32 -> 16-bit Int16）、RMS 能量与分贝换算、以及平滑连续帧前端 VAD 状态机；
- `useVoiceStreamStore.ts`: 基于 Zustand 的集中式响应状态机，调度全双工对讲开启/关闭、音频流输入处理、实时能量波形统计与错误兜底；
- `VoiceStreamControllerCard.tsx`: 现代化工业级交互卡片，提供安全状态徽章、Autoplay 一键解锁条、动态波形能量条、VAD 说话态指示器、全双工对讲主控按键与环境自愈折叠看板。

## 3. 工程质量与安全红线守则
- **零 any 约束**：全量代码均使用严格强类型约束；
- **单文件行数受控**：各文件行数均严格控制在 300 行以内（远低于 400 行红线）；
- **零原生 emoji**：全部采用统一的 Lucide 矢量图标；
- **全括号与代码健壮性**：所有 `if` 均显式包裹 `{}`；
- **无障碍访问 a11y**：严格使用语义化 `<output>`、`<section>` 及关联 `<label>`。
