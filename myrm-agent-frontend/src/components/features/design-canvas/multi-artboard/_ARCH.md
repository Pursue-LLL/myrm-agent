# Multi-Artboard Panoramic Studio & Zero-Token Prototype Player Architecture

## Overview
多画板全景平铺一览与免 Token 原型交互播放套件，包含：
- `multiArtboardTypes.ts`: 画板、交互跳转连线、视觉风格锁与免 Token 播放器契约；
- `artboardLayoutEngine.ts`: 网格流式平铺排布算法、贝塞尔交互跳转曲线计算与主题一致性锁应用；
- `useMultiArtboardStore.ts`: Zustand 多画板与播放状态机驱动；
- `MultiArtboardCanvasViewport.tsx`: 2D 缩放平移视口、多画板实体与流转连线 SVG 渲染；
- `CrossArtboardThemeLockBar.tsx`: 风格锁栏、调色板预设与播放器入口；
- `InteractivePrototypePlayerModal.tsx`: 多外壳真机交互走查与热区指示器。
