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
  | 'llm_map'
  | 'answer_tool';

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
  'llm_map',
  'answer_tool',
] as const;

export const DEFAULT_ENABLED_BUILTIN_TOOLS: BuiltinToolId[] = ['web_search', 'memory'];
