/**
 * 预置智能体类型定义
 *
 * 预置智能体是系统内置的智能体模板，包括：
 * - 通用助手（通用对话）
 * - CLI 可视化智能体（支持 Claude Code、Codex、Gemini CLI 等）
 */

/** 预置智能体类别 */
export type PresetAgentCategory = 'general' | 'cli_visual';

/** 预置智能体定义 */
export interface PresetAgent {
  /** 唯一标识符 */
  id: string;

  /** 显示名称 */
  name: string;

  /** 类别 */
  category: PresetAgentCategory;

  /** 图标名称（Lucide icon） */
  icon: string;

  /** 是否可用（依赖外部配置） */
  isAvailable?: boolean;

  // ==================== 通用智能体配置 ====================

  /** 系统提示词 */
  systemPrompt?: string;

  /** 启用的技能列表 */
  skillIds?: string[];
}
