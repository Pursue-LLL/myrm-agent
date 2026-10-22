# Artifact Adaptive Audio Digest & Continuation Capsule Architecture (`audio-digest/podcast-capsule`)

## 1. 架构定位与业务痛点
针对用户在下楼买咖啡、通勤或开车碎片化移动场景下，无法舒适阅读 Agent 产出的万字复杂长篇深度报告/工件，以及小屏（可穿戴手表/手机）与大屏深度消费断层的痛点，本模块提供自适应口语化音频播客简报引擎（60~120秒高信噪比双人对白/核心要点听觉消费）与跨端连续性流转胶囊（从小屏听觉到大屏视觉图表细读的无缝接力）。

## 2. 模块拓扑与职责划分
- **`audioDigestTypes.ts`**：定义播客分段契约 `PodcastSegment`（说话人角色、时间戳范围、源章节标题与目标锚点）、音频简报模型 `ArtifactAudioDigest`、连续性流转胶囊模型 `ContinuationCapsule` 与恢复结果；
- **`podcastSynthesizerEngine.ts`**：纯函数引擎，支持时间格式化（`mm:ss`）、当前秒数快速定位当前播客段落、大屏连续性流转胶囊构造与时效性校验；
- **`useAudioDigestStore.ts`**：Zustand 集中式状态总线，管理播放进度、播放速率（1x/1.25x/1.5x/2x）、段落高亮切换与大屏恢复事件广播（`myrm:audio-digest-segment-change` 与 `myrm:capsule-continuation-resumed`）；
- **`ArtifactAudioDigestPlayerCard.tsx`**：工件口语化音频随身听卡片，具备波形跳动模拟、倍速调节、时间进度跳转与口语化逐句对白字幕滚动聚焦；
- **`ContinuationCapsuleModal.tsx`**：跨端流转胶囊弹窗，展示收听进度时戳、对应工件目标锚点、扫码流转二维码与一键在大屏定位接力恢复。

## 3. 极不友好 Code Review 12 项清单遵循度
1. **零 Any**：全强类型契约设计；
2. **零原生 Emoji**：全部采用 Lucide 矢量图标（`Headphones`, `Mic`, `Volume2`, `QrCode`, `Sparkles` 等）；
3. **前端所有 If 显式带大括号**：严格杜绝无括号单行写法；
4. **单文件行数严格受控**：各文件行数受控在 290 行以内（远低于 400 行红线）；
5. **a11y 无障碍标准**：符合 HTML5 语义化（采用原生 dialog 标签）、键盘交互与触控目标尺寸。
