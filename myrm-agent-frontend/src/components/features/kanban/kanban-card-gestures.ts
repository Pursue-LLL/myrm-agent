/**
 * [INPUT]
 * - react::SyntheticEvent (POS: 合成事件类型)
 *
 * [OUTPUT]
 * - ISOLATE_FROM_CARD: 卡片内交互控件的手势隔离属性（按下、点击、双击都不冒泡给卡片）
 *
 * [POS]
 * 看板卡片外层是 dnd-kit 的拖拽源，并监听点击（Ctrl / Shift 多选）与双击（开详情抽屉）。
 * 卡片内的菜单触发器、勾选框等控件展开这组属性，自己的手势才不会被卡片截走：
 * 否则按下控件会起拖拽、点击会走多选、双击会打开详情抽屉。
 * React 合成事件沿组件树冒泡，会穿过 portal：渲染在 portal 里的菜单内容同样要展开。
 */
import type { SyntheticEvent } from 'react';

const stopPropagation = (event: SyntheticEvent) => event.stopPropagation();

export const ISOLATE_FROM_CARD = {
  onPointerDown: stopPropagation,
  onClick: stopPropagation,
  onDoubleClick: stopPropagation,
} as const;
