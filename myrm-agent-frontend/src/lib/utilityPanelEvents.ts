/**
 * [INPUT] 无
 *
 * [OUTPUT] UTILITY_PANEL_EVENTS: 次级工具面板的全局打开事件名 SSOT
 *          UtilityPanelId: 事件名对应的面板 ID
 *
 * [POS] 菜单与面板之间的事件契约。派发方和监听方共用同一份常量，避免字符串各写一份后失配。
 */

export const UTILITY_PANEL_EVENTS = {
  workbench: 'myrm:open-workbench',
  sessionMap: 'myrm:open-session-map',
  presentation: 'myrm:open-presentation',
  toolPicker: 'myrm:open-tool-picker',
  assistant: 'myrm:open-system-assistant',
} as const;

export type UtilityPanelId = keyof typeof UTILITY_PANEL_EVENTS;
