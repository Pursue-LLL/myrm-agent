/**
 * [INPUT] zod (POS: 表单校验), @/services/agent::Agent, AgentCreate, AgentSessionPolicy, AgentType, CommandBindingConfig (POS: 智能体领域类型)
 * [OUTPUT] agentSchema, AgentFormData, EMPTY_FORM_VALUES, AgentExtraFields, EMPTY_EXTRA_FIELDS, formValuesFromAgent, extraFieldsFromAgent, buildAgentPayload: 智能体编辑表单的校验规则、非 react-hook-form 字段模型、详情回填与提交载荷
 * [POS] AgentEditForm 的纯逻辑层；新建模式用空值回填全部字段，浏览器与会话字段取默认值时以 null 提交，由服务端沿用全局策略。
 */

import * as z from 'zod';
import type { Agent, AgentCreate, AgentSessionPolicy, AgentType, CommandBindingConfig } from '@/services/agent';

export const agentSchema = z.object({
  name: z.string().min(1, 'Name is required').max(50, 'Name must be less than 50 characters'),
  description: z.string().max(200, 'Description must be less than 200 characters').optional(),
  system_prompt: z.string().max(10000, 'System prompt is too long').optional(),
  avatar_url: z.string().optional(),
});

export type AgentFormData = z.infer<typeof agentSchema>;

export const EMPTY_FORM_VALUES: AgentFormData = {
  name: '',
  description: '',
  system_prompt: '',
  avatar_url: '',
};

const DEFAULT_SESSION_POLICY: AgentSessionPolicy = { mode: 'daily', daily_reset_hour: 4, idle_minutes: 120 };

/** At most this many acceptance-checklist lines are submitted. */
const MAX_ACCEPTANCE_CRITERIA = 20;

/** Fields edited outside react-hook-form. */
export interface AgentExtraFields {
  commandBindings: CommandBindingConfig[];
  agentType: AgentType;
  sessionPolicyEnabled: boolean;
  sessionPolicy: AgentSessionPolicy;
  browserSource: string;
  dialogPolicy: string;
  sessionRecording: string;
  responsibilityScope: string;
  ownerLabel: string;
  acceptanceCriteriaText: string;
}

export const EMPTY_EXTRA_FIELDS: AgentExtraFields = {
  commandBindings: [],
  agentType: 'individual',
  sessionPolicyEnabled: false,
  sessionPolicy: DEFAULT_SESSION_POLICY,
  browserSource: 'auto',
  dialogPolicy: 'smart',
  sessionRecording: 'off',
  responsibilityScope: '',
  ownerLabel: '',
  acceptanceCriteriaText: '',
};

export function formValuesFromAgent(agent: Agent): AgentFormData {
  return {
    name: agent.name,
    description: agent.description || '',
    system_prompt: agent.system_prompt || '',
    avatar_url: agent.avatar_url || '',
  };
}

export function extraFieldsFromAgent(agent: Agent): AgentExtraFields {
  return {
    commandBindings: agent.command_bindings || [],
    agentType: agent.agent_type || 'individual',
    sessionPolicyEnabled: Boolean(agent.session_policy),
    sessionPolicy: agent.session_policy || DEFAULT_SESSION_POLICY,
    browserSource: agent.browser_source || 'auto',
    dialogPolicy: agent.dialog_policy || 'smart',
    sessionRecording: agent.session_recording || 'off',
    responsibilityScope: agent.responsibility_scope || '',
    ownerLabel: agent.owner_label || '',
    acceptanceCriteriaText: (agent.acceptance_criteria || []).join('\n'),
  };
}

export function buildAgentPayload(data: AgentFormData, extra: AgentExtraFields): AgentCreate {
  const validBindings = extra.commandBindings.filter((b) => b.command_name && b.skill_ids.length > 0);
  const acceptanceCriteria = extra.acceptanceCriteriaText
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .slice(0, MAX_ACCEPTANCE_CRITERIA);
  return {
    ...data,
    agent_type: extra.agentType,
    command_bindings: validBindings.length > 0 ? validBindings : null,
    session_policy: extra.sessionPolicyEnabled ? extra.sessionPolicy : null,
    browser_source: extra.browserSource === 'auto' ? null : extra.browserSource,
    dialog_policy: extra.dialogPolicy === 'smart' ? null : extra.dialogPolicy,
    session_recording: extra.sessionRecording === 'off' ? null : extra.sessionRecording,
    responsibility_scope: extra.responsibilityScope.trim() ? extra.responsibilityScope.trim() : null,
    owner_label: extra.ownerLabel.trim() ? extra.ownerLabel.trim() : null,
    acceptance_criteria: acceptanceCriteria.length > 0 ? acceptanceCriteria : null,
  };
}
