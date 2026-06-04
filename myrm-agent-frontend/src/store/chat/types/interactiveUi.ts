/**
 * [INPUT]
 * @/store/config/providerTypes::SingleModelSelection (POS: Provider/model selection type contract)
 *
 * [OUTPUT]
 * Chat message, stream event, artifact, memory citation and store state TypeScript contracts.
 *
 * [POS]
 * Chat state and SSE event type definitions. Split from monolithic types.ts for maintainability.
 */

// ==================== 交互式 UI 类型定义 (A2UI 风格) ====================

// 支持的 UI 组件类型（安全白名单）
export type UIComponentType =
  // 基础组件
  | 'text'
  | 'button'
  | 'button_group'
  // 表单组件
  | 'text_field'
  | 'textarea'
  | 'select'
  | 'date_picker'
  | 'time_picker'
  | 'slider'
  | 'checkbox'
  | 'radio'
  | 'switch'
  // 布局组件
  | 'container'
  | 'card'
  | 'divider'
  | 'grid'
  | 'tabs'
  // 数据展示组件
  | 'table'
  | 'list'
  | 'image'
  | 'chart'
  | 'progress'
  | 'badge';

// UI 组件声明
export interface UIComponent {
  id: string; // 组件唯一标识符
  type: UIComponentType; // 组件类型
  props: Record<string, unknown>; // 组件属性
  children: string[]; // 子组件 ID 列表
  bindings: Record<string, string>; // 数据绑定 (prop -> dataPath)
  events: Record<string, string>; // 事件绑定 (eventName -> actionId)
}

// UI 动作定义
export interface UIAction {
  id: string; // 动作唯一标识符
  type: 'submit' | 'cancel' | 'navigate' | 'custom'; // 动作类型
  label: string; // 动作显示文本
  payload: Record<string, unknown>; // 额外载荷数据
}

// 交互式 UI 工件
export interface UIArtifact {
  surface_id: string; // Surface 标识符
  title?: string; // UI 标题
  components: UIComponent[]; // 组件列表（扁平邻接表）
  root_ids: string[]; // 根组件 ID 列表
  data: Record<string, unknown>; // 数据模型
  actions: UIAction[]; // 可触发的动作
}

// UI 数据增量更新
export interface UIDataUpdate {
  surface_id: string; // 目标 Surface 标识符
  updates: Record<string, unknown>; // 数据更新
}

// 用户动作事件（回传给 Agent）
export interface UIActionEvent {
  surface_id: string; // 来源 Surface 标识符
  action_id: string; // 触发的动作 ID
  action_type: string; // 动作类型
  data: Record<string, unknown>; // 当前 UI 的数据状态
  payload: Record<string, unknown>; // 动作携带的额外数据
}
