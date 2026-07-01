/**
 * [OUTPUT]
 * BuiltinToolId, BUILTIN_TOOL_IDS, DEFAULT_ENABLED_BUILTIN_TOOLS.
 * 
 * [POS]
 * 内置工具 ID 常量。
 */

// ---------------------------------------------------------------------------
// 内置工具 ID 常量
// ---------------------------------------------------------------------------

export type BuiltinToolId =
  | 'web_search'
  | 'memory'
  | 'file_ops'
  | 'code_execute'
  | 'wiki'
  | 'browser'
  | 'computer_use'
  | 'image_generation'
  | 'video_generation'
  | 'tts'
  | 'kanban'
  | 'canvas'
  | 'answer_tool'
  | 'render_ui';

export const BUILTIN_TOOL_IDS: readonly BuiltinToolId[] = [
  'web_search',
  'memory',
  'file_ops',
  'code_execute',
  'wiki',
  'browser',
  'computer_use',
  'image_generation',
  'video_generation',
  'tts',
  'kanban',
  'canvas',
  'answer_tool',
  'render_ui',
] as const;

export const DEFAULT_ENABLED_BUILTIN_TOOLS: BuiltinToolId[] = ['web_search', 'memory'];
