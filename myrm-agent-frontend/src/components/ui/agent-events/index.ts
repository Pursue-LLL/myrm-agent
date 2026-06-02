/**
 * Agent Events Components
 *
 * 仅 Tauri/Self-hosted 模式显示的事件可视化组件
 */

export { EventTimeline, EventTimelineLoading, type AgentEvent, type EventLevel, type EventType } from './EventTimeline';

export {
  PermissionDialog,
  PermissionModeSelector,
  type PendingPermission,
  type PermissionMode,
  type RiskLevel,
} from './PermissionDialog';
