/**
 * 工具图标映射 - 按大类分组
 *
 * 设计理念：按用户视角的操作类型分类，而非为每个工具单独设置图标
 * - 思考分析：AI 正在思考、规划、生成答案
 * - 信息检索：搜索网页、查阅资料
 * - 文件操作：读写编辑文件
 * - 代码执行：运行代码、执行命令
 * - 记忆存储：存储记忆、更新画像
 * - 图像生成：AI 图片生成与编辑
 * - 视频生成：AI 视频生成
 * - 工具调用：MCP 等扩展工具
 *
 * 使用 Hugeicons - 现代化风格，完全合规的 MIT 许可证
 */

import React from 'react';
import {
  Search01Icon,
  File01Icon,
  Atom01Icon,
  Database01Icon,
  ToolsIcon,
  CodeIcon,
  MagicWand02Icon,
  AiVideoIcon,
  Shield02Icon,
} from 'hugeicons-react';

// 工具类别定义
export type ToolCategory =
  | 'thinking' // 思考分析
  | 'search' // 信息检索
  | 'file' // 文件操作
  | 'execute' // 代码执行
  | 'storage' // 记忆存储
  | 'image' // 图像生成
  | 'video' // 视频生成
  | 'safety' // 安全降级
  | 'tool'; // 工具调用

// Agent主题颜色类型
export type AgentThemeColor = 'blue' | 'green' | 'purple' | 'orange' | 'pink' | 'cyan' | 'amber' | 'red';

// Agent颜色映射（Tailwind类名）
export const AGENT_COLOR_CLASSES: Record<
  AgentThemeColor,
  {
    text: string;
    bg: string;
    border: string;
    badge: string;
  }
> = {
  blue: {
    text: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-950/20',
    border: 'border-blue-300 dark:border-blue-800/40',
    badge: 'bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400',
  },
  green: {
    text: 'text-green-600 dark:text-green-400',
    bg: 'bg-green-50 dark:bg-green-950/20',
    border: 'border-green-300 dark:border-green-800/40',
    badge: 'bg-green-500/10 border-green-500/30 text-green-600 dark:text-green-400',
  },
  purple: {
    text: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-50 dark:bg-purple-950/20',
    border: 'border-purple-300 dark:border-purple-800/40',
    badge: 'bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400',
  },
  orange: {
    text: 'text-orange-600 dark:text-orange-400',
    bg: 'bg-orange-50 dark:bg-orange-950/20',
    border: 'border-orange-300 dark:border-orange-800/40',
    badge: 'bg-orange-500/10 border-orange-500/30 text-orange-600 dark:text-orange-400',
  },
  pink: {
    text: 'text-pink-600 dark:text-pink-400',
    bg: 'bg-pink-50 dark:bg-pink-950/20',
    border: 'border-pink-300 dark:border-pink-800/40',
    badge: 'bg-pink-500/10 border-pink-500/30 text-pink-600 dark:text-pink-400',
  },
  cyan: {
    text: 'text-cyan-600 dark:text-cyan-400',
    bg: 'bg-cyan-50 dark:bg-cyan-950/20',
    border: 'border-cyan-300 dark:border-cyan-800/40',
    badge: 'bg-cyan-500/10 border-cyan-500/30 text-cyan-600 dark:text-cyan-400',
  },
  amber: {
    text: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-950/20',
    border: 'border-amber-300 dark:border-amber-800/40',
    badge: 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400',
  },
  red: {
    text: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-50 dark:bg-red-950/20',
    border: 'border-red-300 dark:border-red-800/40',
    badge: 'bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400',
  },
};

// 默认Agent颜色调色板（用于自动分配）
export const DEFAULT_AGENT_COLORS: AgentThemeColor[] = ['blue', 'green', 'purple', 'orange', 'pink', 'cyan'];

/**
 * 根据agent_instance自动分配颜色
 * @param agent_instance Agent实例标识（如"research_agent-a1b2"）
 * @param agentIndex Agent在列表中的索引（可选，用于更均匀的颜色分布）
 * @returns Agent主题颜色
 */
export const getAgentColor = (agent_instance: string | undefined, agentIndex?: number): AgentThemeColor => {
  if (!agent_instance) return 'blue';

  // 如果提供了索引，使用索引分配颜色（更均匀）
  if (typeof agentIndex === 'number') {
    return DEFAULT_AGENT_COLORS[agentIndex % DEFAULT_AGENT_COLORS.length];
  }

  // 否则根据agent_instance哈希分配
  let hash = 0;
  for (let i = 0; i < agent_instance.length; i++) {
    hash = (hash << 5) - hash + agent_instance.charCodeAt(i);
    hash = hash & hash;
  }
  const index = Math.abs(hash) % DEFAULT_AGENT_COLORS.length;
  return DEFAULT_AGENT_COLORS[index];
};

/**
 * 格式化agent_instance为@handle格式
 * @param agent_instance Agent实例标识
 * @param display_name 自定义显示名称（优先使用）
 * @returns 格式化的显示名称
 */
export const formatAgentHandle = (agent_instance: string | undefined, display_name?: string): string => {
  if (display_name) {
    // 如果已经有@前缀，直接返回
    return display_name.startsWith('@') ? display_name : `@${display_name}`;
  }

  if (!agent_instance) return '';

  // 提取agent_type部分（如"research_agent-a1b2" -> "research"）
  const agentType = agent_instance.split('-')[0].replace(/_agent$/, '');
  const shortId = agent_instance.split('-')[1] || '';

  // 转换为首字母大写的友好格式
  const friendlyName = agentType
    .replace(/_/g, ' ')
    .split(' ')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join('');

  return shortId ? `@${friendlyName}-${shortId}` : `@${friendlyName}`;
};

// Hugeicons 组件类型
type HugeIconComponent = React.FC<{
  size?: number;
  color?: string;
  className?: string;
}>;

// 类别图标映射 - 使用 Hugeicons
export const CATEGORY_ICON_MAP: Record<ToolCategory, HugeIconComponent> = {
  thinking: Atom01Icon,
  search: Search01Icon,
  file: File01Icon,
  execute: CodeIcon,
  storage: Database01Icon,
  image: MagicWand02Icon,
  video: AiVideoIcon,
  safety: Shield02Icon,
  tool: ToolsIcon,
};

// 工具名称 -> 类别映射
export const TOOL_CATEGORY_MAP: Record<string, ToolCategory> = {
  // 信息检索类
  web_search_tool: 'search',
  web_fetch_tool: 'search',

  // 文件操作类
  file_read_tool: 'file',
  file_write_tool: 'file',
  file_edit_tool: 'file',
  file_editor_tool: 'file',
  file_editor_view_tool: 'file',
  file_editor_create_tool: 'file',
  file_editor_edit_tool: 'file',
  text_editor_tool: 'file',

  // 代码执行类
  bash_code_execute_tool: 'execute',
  code_execution_tool: 'execute',
  execute_code: 'execute',

  // 思考分析类
  skill_select_tool: 'thinking',
  render_ui_tool: 'thinking',
  answer_user_tool: 'thinking',
  request_answer_user_tool: 'thinking',

  // 记忆存储类
  memory_search_tool: 'storage',
  memory_store_tool: 'storage',
  memory_save_tool: 'storage',
  memory_manage_tool: 'storage',
  memory_recall_tool: 'storage',
  profile_get_tool: 'storage',
  profile_update_tool: 'storage',

  // 图像生成类
  image_tool: 'image',

  // 视频生成类
  video_tool: 'video',

  // 工具调用类
  mcp_tool: 'tool',
};

// 系统步骤 -> 类别映射
export const SYSTEM_STEP_CATEGORY_MAP: Record<string, ToolCategory> = {
  analyzing_query: 'thinking',
  analyzing_image: 'thinking',
  reviewing_sources: 'search',
  planning_task: 'thinking',
  generating_answer: 'thinking',
  subagent_running: 'thinking',
  swarm_fission: 'thinking',
  subagent_notification: 'thinking',
  safety_fallback_active: 'safety',
  context_pruned: 'thinking',
  archive_checkpoint: 'thinking',
  memory_archived: 'thinking',
};

// 默认类别
export const DEFAULT_CATEGORY: ToolCategory = 'tool';

/**
 * 获取步骤图标（基于分类系统）
 * @param step_key 步骤标识符
 * @param tool_name 工具名称（null 表示系统步骤）
 * @returns Hugeicons 图标组件
 */
export const getStepIcon = (step_key: string, tool_name: string | null | undefined): HugeIconComponent => {
  // 系统步骤（tool_name 为 null）
  if (tool_name === null || tool_name === undefined) {
    const category = SYSTEM_STEP_CATEGORY_MAP[step_key] || DEFAULT_CATEGORY;
    return CATEGORY_ICON_MAP[category];
  }

  // 工具调用
  const category = TOOL_CATEGORY_MAP[tool_name] || DEFAULT_CATEGORY;
  return CATEGORY_ICON_MAP[category];
};

/**
 * 获取步骤类别
 * @param step_key 步骤标识符
 * @param tool_name 工具名称（null 表示系统步骤）
 * @returns 工具类别
 */
export const getStepCategory = (step_key: string, tool_name: string | null | undefined): ToolCategory => {
  if (tool_name === null || tool_name === undefined) {
    return SYSTEM_STEP_CATEGORY_MAP[step_key] || DEFAULT_CATEGORY;
  }
  return TOOL_CATEGORY_MAP[tool_name] || DEFAULT_CATEGORY;
};

/**
 * 判断是否为系统步骤
 * @param tool_name 工具名称
 * @returns 是否为系统步骤
 */
export const isSystemStep = (tool_name: string | null | undefined): boolean => {
  return tool_name === null || tool_name === undefined;
};

/**
 * StepIcon 组件 - 渲染步骤图标（使用 Hugeicons）
 */
interface StepIconProps {
  step_key: string;
  tool_name: string | null | undefined;
  size?: number;
  className?: string;
}

export const StepIcon: React.FC<StepIconProps> = ({ step_key, tool_name, size = 18, className = '' }) => {
  const Icon = getStepIcon(step_key, tool_name);
  const isSystem = isSystemStep(tool_name);

  return <Icon size={size} className={className || (isSystem ? 'text-primary/70' : 'text-foreground/80')} />;
};
