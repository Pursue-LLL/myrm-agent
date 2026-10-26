/**
 * [INPUT] 无
 *
 * [OUTPUT] OPEN_VISUAL_DESKTOP_EVENT: 打开可视化桌面面板的全局事件名 SSOT
 *          OpenVisualDesktopDetail: 事件载荷（takeover=true 表示用户要同时接管操作）
 *          openVisualDesktop: 派发该事件
 *
 * [POS] 浏览器 Inspector / 子 Agent 视口与可视化桌面面板之间的事件契约。派发方和监听方共用同一份常量与载荷类型。
 */

export const OPEN_VISUAL_DESKTOP_EVENT = 'open_visual_desktop';

export interface OpenVisualDesktopDetail {
  takeover?: boolean;
}

export function openVisualDesktop(detail: OpenVisualDesktopDetail = {}): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent<OpenVisualDesktopDetail>(OPEN_VISUAL_DESKTOP_EVENT, { detail }));
}
