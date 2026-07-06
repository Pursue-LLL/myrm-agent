/**
 * [OUTPUT]
 * BuiltinToolId, BUILTIN_TOOL_IDS, DEFAULT_ENABLED_BUILTIN_TOOLS.
 *
 * [POS]
 * 内置工具 ID 常量。file_ops / code_execute 为 Agent 基线能力，由服务端强制加载，不在 UI 展示。
 */

// ---------------------------------------------------------------------------
// 内置工具 ID 常量（GUI 可切换项；Fast 模式工具由服务端写死）
// ---------------------------------------------------------------------------

export type BuiltinToolId =
  | 'web_search'
  | 'memory'
  | 'wiki'
  | 'browser'
  | 'computer_use'
  | 'image_generation'
  | 'video_generation'
  | 'tts'
  | 'kanban'
  | 'canvas'
  | 'cron'
  | 'answer_tool'
  | 'render_ui'
  | 'planning';

export const BUILTIN_TOOL_IDS: readonly BuiltinToolId[] = [
  'web_search',
  'memory',
  'wiki',
  'browser',
  'computer_use',
  'image_generation',
  'video_generation',
  'tts',
  'kanban',
  'canvas',
  'cron',
  'answer_tool',
  'render_ui',
  'planning',
] as const;

export const DEFAULT_ENABLED_BUILTIN_TOOLS: BuiltinToolId[] = [
  'web_search',
  'memory',
];
