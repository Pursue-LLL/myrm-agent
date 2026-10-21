/**
 * 预置智能体类型定义
 *
 * 预置智能体是系统内置的智能体模板，包括：
 * - 通用助手（通用对话）
 * - CLI 可视化智能体（支持 Claude Code、Codex、Gemini CLI 等）
 */

/** 预置智能体类别 */
export type PresetAgentCategory = 'general' | 'cli_visual';

/** 快捷任务定义 - 作为教程展示给用户 */
export interface QuickTask {
  /** 唯一标识符 */
  id: string;

  /** 任务名称 */
  name: string;

  /** 任务名称的国际化 key */
  nameKey: string;

  /** 任务指引/说明 */
  guide: string;

  /** 任务指引的国际化 key */
  guideKey: string;

  /** 图标名称（Lucide icon） */
  icon?: string;
}

/** 预置智能体定义 */
export interface PresetAgent {
  /** 唯一标识符 */
  id: string;

  /** 显示名称 */
  name: string;

  /** 英文名称（用于国际化） */
  nameKey: string;

  /** 描述 */
  description: string;

  /** 英文描述（用于国际化） */
  descriptionKey: string;

  /** 类别 */
  category: PresetAgentCategory;

  /** 图标名称（Lucide icon） */
  icon: string;

  /** 是否可用（依赖外部配置） */
  isAvailable?: boolean;

  /** 可用性检查函数名 */
  availabilityCheck?: string;

  /** 快捷任务列表 - 作为教程展示 */
  quickTasks?: QuickTask[];

  // ==================== CLI 可视化智能体特有配置 ====================

  /** 是否需要工作目录（CLI 可视化智能体必需） */
  requiresWorkingDirectory?: boolean;

  /** 默认工作目录（可选） */
  defaultWorkingDirectory?: string;

  // ==================== 通用智能体配置 ====================

  /** 系统提示词 */
  systemPrompt?: string;

  /** 启用的工具列表 */
  tools?: string[];

  /** 启用的技能列表 */
  skillIds?: string[];
}

/** 预置智能体配置集合 */
export interface PresetAgentConfig {
  /** 所有预置智能体 */
  agents: PresetAgent[];

  /** 按类别分组 */
  categories: {
    id: PresetAgentCategory;
    name: string;
    nameKey: string;
  }[];
}

/** 获取已启用的预置智能体 */
export type GetEnabledPresetAgents = () => PresetAgent[];

/** 检查预置智能体是否可用 */
export type CheckPresetAgentAvailability = (agentId: string) => boolean;
