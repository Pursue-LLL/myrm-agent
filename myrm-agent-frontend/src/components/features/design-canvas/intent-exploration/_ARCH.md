# Design Intent Five-Element Auto Alignment & Multi-Direction Exploration Architecture

## Overview
设计意图五要素反向对齐、交互式要素胶囊与多方向初稿铺开探索套件，包含：
- `designIntentTypes.ts`: 五要素契约（做什么、给谁看、什么风格、内容清单、尺寸用途）、变体与完整度模型；
- `fiveElementLinterEngine.ts`: 意图语义检测分析引擎、商业设计 Prompt 自动升华组装器与 3 方向变体发散生成器；
- `useDesignIntentStore.ts`: Zustand 状态机，驱动胶囊交互、快速补全与 3 方向选型决策；
- `FiveElementCapsuleBar.tsx`: 交互式微要素胶囊条、完备度评分指示徽章与 Prompt 升华快捷入口；
- `MultiDirectionDivergenceDeck.tsx`: 3 方向初稿横向平铺探索展台（极简留白 / 视觉冲击 / 结构卡片）与「选择此方向深化」单选决策流。
