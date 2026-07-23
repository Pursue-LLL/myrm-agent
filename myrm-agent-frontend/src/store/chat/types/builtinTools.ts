/**
 * [OUTPUT]
 * BuiltinToolId, BUILTIN_TOOL_IDS, BUILTIN_TOOL_LABELS, DEFAULT_ENABLED_BUILTIN_TOOLS,
 * isBuiltinToolId, getBuiltinToolDisplayLabel, resolveToolSnapshotDisplayName.
 *
 * [POS]
 * GUI 可切换 builtin 产品 ID 与本地化 capability 标签 SSOT（gap toast + wrench 面板共用）。
 * file_ops / code_execute 为 General Agent 基线（harness CORE），服务端 tool_mount.resolve_agent_mount 强制加载，不在 UI 展示。
 * Search/Fast（无 file/bash）仅 Web action_mode=fast；Channel/IM 仅绑定 General Agent。
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
  | 'cron'
  | 'answer_tool'
  | 'render_ui'
  | 'planning'
  | 'structured_clarify'
  | 'external_cli'
  | 'web_crawl';

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
  'cron',
  'answer_tool',
  'render_ui',
  'planning',
  'structured_clarify',
  'external_cli',
  'web_crawl',
] as const;

export const DEFAULT_ENABLED_BUILTIN_TOOLS: BuiltinToolId[] = [
  'web_search',
  'memory',
  'structured_clarify',
];

const BUILTIN_TOOL_ID_SET = new Set<string>(BUILTIN_TOOL_IDS);

export function isBuiltinToolId(value: string): value is BuiltinToolId {
  return BUILTIN_TOOL_ID_SET.has(value);
}

/** Localized GUI labels for togglable builtin capabilities (SSOT for gap toast + wrench panel). */
export const BUILTIN_TOOL_LABELS: Record<BuiltinToolId, { en: string; zh: string }> = {
  web_search: { en: 'Web Search', zh: '网页搜索' },
  memory: { en: 'Memory', zh: '记忆' },
  wiki: { en: 'Wiki', zh: 'Wiki' },
  browser: { en: 'Browser', zh: '浏览器' },
  computer_use: { en: 'Computer Use', zh: '桌面控制' },
  image_generation: { en: 'Image Generation', zh: '图片生成' },
  video_generation: { en: 'Video Generation', zh: '视频生成' },
  tts: { en: 'Text to Speech', zh: '语音合成' },
  kanban: { en: 'Kanban', zh: '看板' },
  cron: { en: 'Scheduled Tasks', zh: '定时任务' },
  answer_tool: { en: 'Answer Tool', zh: '答案工具' },
  render_ui: { en: 'Render UI', zh: 'UI 渲染' },
  planning: { en: 'Planning', zh: '任务规划' },
  structured_clarify: { en: 'Structured Clarify', zh: '结构化澄清' },
  external_cli: { en: 'External CLI', zh: '外部 CLI' },
  web_crawl: { en: 'Site Crawl', zh: '整站爬取' },
};

export function getBuiltinToolDisplayLabel(
  toolId: BuiltinToolId,
  locale: 'en' | 'zh',
): string {
  return locale === 'zh' ? BUILTIN_TOOL_LABELS[toolId].zh : BUILTIN_TOOL_LABELS[toolId].en;
}

export function resolveToolSnapshotDisplayName(
  tool: { name: string; builtin_tool_id?: string | null },
  locale: 'en' | 'zh',
  knownToolDisplayName?: string,
): string {
  if (knownToolDisplayName) {
    return knownToolDisplayName;
  }
  const productId = tool.builtin_tool_id;
  if (productId && isBuiltinToolId(productId)) {
    return getBuiltinToolDisplayLabel(productId, locale);
  }
  return tool.name;
}
