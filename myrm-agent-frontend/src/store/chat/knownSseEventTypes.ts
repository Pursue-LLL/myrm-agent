/**
 * [INPUT]
 * ./types::AgentEventType (POS: SSE 事件类型前半段；与后端 AgentEventType 对齐)
 *
 * [OUTPUT]
 * KNOWN_SSE_EVENT_TYPE_VALUES, normalizeSseEventType, HARNESS_SSE_EVENT_ALIASES
 *
 * [POS]
 * 允许进入 reducer 的 SSE type 白名单；与 harness AgentEventType StrEnum 对齐。
 */

import { AgentEventType } from './types';

/** Values from myrm_agent_harness.core.events.types.AgentEventType (keep in sync). */
export const HARNESS_AGENT_EVENT_TYPE_VALUES = [
  'tasks_steps',
  'tool_heartbeat',
  'sources',
  'message',
  'message_end',
  'error',
  'cancelled',
  'artifacts',
  'artifacts_ready',
  'ui_update',
  'tool_start',
  'tool_end',
  'tool_failure',
  'tool_stdout_chunk',
  'tool_evicted_ref',
  'tool_cancelled',
  'tool_timeout',
  'tool_retry',
  'tool_token_usage',
  'artifact_content',
  'token_usage',
  'approval_intercepted',
  'reasoning',
  'steering',
  'tool_approval_request',
  'status',
  'tools_snapshot',
  'async_wakeup',
  'privacy_level',
  'privacy_route',
  'subagent_start',
  'subagent_progress',
  'subagent_log',
  'bash_command_executed',
  'subagent_completion',
  'context_snapshot',
  'iteration_limit_reached',
  'approval_required',
  'clarification_required',
  'cognitive_consolidation',
  'goal_status',
  'engine_limit_reached',
  'client_action',
  'file_diff',
  'captcha_detected',
  'captcha_resolved',
  'captcha_timeout',
  'model_escalated',
  'file_mutation_failed',
  'tool_image_output',
  'browser_view_update',
  'desktop_view_update',
  'ptc_notify',
  'locator_self_healed',
] as const;

/** Harness name → frontend handler type (same payload shape). */
export const HARNESS_SSE_EVENT_ALIASES: Readonly<Record<string, string>> = {
  cancelled: AgentEventType.AGENT_CANCELLED,
};

const frontendValues = Object.values(AgentEventType) as string[];

const merged = new Set<string>([...frontendValues, ...HARNESS_AGENT_EVENT_TYPE_VALUES]);

export const KNOWN_SSE_EVENT_TYPE_VALUES = [...merged].sort() as [
  string,
  ...string[],
];

export function normalizeSseEventType(type: string): string {
  return HARNESS_SSE_EVENT_ALIASES[type] ?? type;
}

export function isKnownSseEventType(type: string): boolean {
  const normalized = normalizeSseEventType(type);
  return merged.has(type) || merged.has(normalized);
}
