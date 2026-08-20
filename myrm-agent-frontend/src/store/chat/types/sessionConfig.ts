/**
 * [INPUT]
 * @/store/config/providerTypes::SingleModelSelection (POS: Provider/model selection type contract)
 * ./builtinTools::BuiltinToolId (POS: 内置工具 ID 常量)
 *
 * [OUTPUT]
 * ActionMode, AgentConfig, SelectedModels, ModelSelection.
 *
 * [POS]
 * 会话级 Agent 与模式配置类型。
 */

import type { RoutingConfig, SingleModelSelection } from '@/store/config/providerTypes';
import type { AgentSkillConfigMap } from '@/types/agentSkillConfig';
import type { BuiltinToolId } from './builtinTools';

// 操作模式类型
export type ActionMode = 'fast' | 'agent' | 'deep_research' | 'claude_code';

export type BusyInputMode = 'redirect' | 'steer' | 'queue';

// 快速搜索深度类型
export type SearchDepth = 'normal' | 'deep';

export interface ModelSelection {
  providerId: string;
  model: string;
  baseUrl?: string;
  modelKwargs?: Record<string, unknown>;
  supportsVision?: boolean;
  credentialPoolStrategy?: string;
}

// 智能体配置
export interface AgentConfig {
  selectedSkillIds: string[];
  skillConfigs?: AgentSkillConfigMap;
  selectedMcpNames: string[];
  systemPrompt: string;
  useGlobalInstruction: boolean;
  autoRestoreDomains?: string[]; // 自动恢复的浏览器身份域名列表
  // 已保存智能体信息（用于追踪和更新）
  agentId?: string;
  agentName?: string;
  agentDescription?: string;
  avatarUrl?: string;
  // 预置智能体信息
  presetId?: string;
  presetName?: string;
  presetIcon?: string;
  modelSelection?: SingleModelSelection | null;
  fallbackModelSelection?: SingleModelSelection | null;
  safetyFallbackModelSelection?: SingleModelSelection | null;
  forceDelegateAgent?: string;
  enabledBuiltinTools?: BuiltinToolId[];
  browserSource?: string;
  dialogPolicy?: 'smart' | 'auto_accept' | 'auto_dismiss' | 'wait_for_agent';
  sessionRecording?: 'off' | 'on_failure' | 'always';
  suggestionPrompts?: string[];
  ephemeralSubagents?: Record<string, unknown>;
  memoryDecayProfile?: 'permanent' | 'normal' | 'fast';
  memoryExtractionPreset?: 'none' | 'auto' | 'persona' | 'work_assistant' | 'research';
  mcpToolSelections?: Record<string, string[]>;
  commandBindings?: { command_name: string; skill_ids: string[]; description?: string; instruction?: string }[];
  routingConfig?: RoutingConfig | null;
  busyInputMode?: BusyInputMode;
  engineParams?: Record<string, unknown> | null;
  /** Agent prompt 模式（full/lean/naked/search），与 server agents.prompt_mode 对齐，用于模型切换压缩预检。 */
  promptMode?: 'full' | 'lean' | 'naked' | 'search';
  /** Agent 默认会话安全预设（hitl/accept_edits/explore）。绑定/切换该 Agent 时用其初始化会话 securityPreset。 */
  defaultSecurityPreset?: 'hitl' | 'accept_edits' | 'explore' | null;
}

// 已选模型配置
export interface SelectedModels {
  base?: string | null;
  vision?: string | null;
  reasoning?: string | null;
}
