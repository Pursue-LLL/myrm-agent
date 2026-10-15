# Multi-Window Command Center HUD & Unified Health Diagnostic Architecture

## Overview
多窗口全局 Command Center HUD、实时多维健康透视与快捷一键运维大厅套件，包含：
- `commandCenterTypes.ts`: 算力大盘、7/30/90 天周期、系统体检检查项与置顶工作流数据契约；
- `commandCenterEngine.ts`: 模糊穿透检索过滤、Token/费用换算、Doctor 全面体检、就地自愈修复与配置快照导出引擎；
- `useCommandCenterHudStore.ts`: Zustand 状态管理，驱动全局快捷键唤出、周期切换、Doctor 诊断运行与置顶流转；
- `CommandCenterHudModal.tsx`: 居中毛玻璃 HUD 视窗，双栏分屏呈现算力用量雷达与系统运维自愈大厅；
- `CommandCenterQuickTriggerButton.tsx`: 顶部状态栏常驻唤出胶囊按钮，显示网关健康呼吸灯与 `Cmd+.` 快捷键。
