/**
 * [INPUT]
 * - ./channelApprovalEvents / skillEvents / systemEvents / alertEvents / goalEvents / agentEvents (POS: 各领域事件处理器表)
 * - @/lib/managedPolicyEffectiveEvents::MANAGED_POLICY_UPDATED_EVENT (POS: 托管策略生效事件名)
 *
 * [OUTPUT]
 * - dispatchGlobalEvent: 按事件类型把服务端推送交给对应处理器；未知类型忽略
 *
 * [POS]
 * 全局事件的分发入口。每个事件类型只有一个处理器；只需唤醒页面的事件在此直接转成 window 事件。
 */
import { MANAGED_POLICY_UPDATED_EVENT } from '@/lib/managedPolicyEffectiveEvents';

import { agentEventHandlers } from './agentEvents';
import { alertEventHandlers } from './alertEvents';
import { channelApprovalEventHandlers } from './channelApprovalEvents';
import type { GlobalEventDeps, GlobalEventHandler, SSEPayload } from './eventTypes';
import { goalEventHandlers } from './goalEvents';
import { skillEventHandlers } from './skillEvents';
import { systemEventHandlers } from './systemEvents';

/** Server events that only wake up pages: event type → name of the window event carrying the payload data. */
const RELAYED_EVENTS: Readonly<Record<string, string>> = {
  memory_history_updated: 'memory_history_updated',
  subagents_updated: 'subagents_updated',
  cron_updated: 'cron_updated',
  budget_updated: 'budget_updated',
  'goal:branch_switched': 'goal:branch_switched',
  workspace_file_changed: 'workspace-file-changed',
  async_agent_stream_chunk: 'async-agent-stream-chunk',
  extension_status_changed: 'extension-status-changed',
  managed_policy_updated: MANAGED_POLICY_UPDATED_EVENT,
};

function relayTo(windowEvent: string): GlobalEventHandler {
  return (payload) => {
    window.dispatchEvent(new CustomEvent(windowEvent, { detail: payload.data }));
  };
}

/** One handler per event type; two tables claiming the same type is a programming error, so it fails at load. */
function buildRegistry(): ReadonlyMap<string, GlobalEventHandler> {
  const registry = new Map<string, GlobalEventHandler>();
  const register = (type: string, handler: GlobalEventHandler): void => {
    if (registry.has(type)) {
      throw new Error(`Duplicate global event handler for "${type}"`);
    }
    registry.set(type, handler);
  };

  const domainTables = [
    channelApprovalEventHandlers,
    skillEventHandlers,
    systemEventHandlers,
    alertEventHandlers,
    goalEventHandlers,
    agentEventHandlers,
  ];
  for (const table of domainTables) {
    for (const [type, handler] of Object.entries(table)) {
      register(type, handler);
    }
  }
  for (const [type, windowEvent] of Object.entries(RELAYED_EVENTS)) {
    register(type, relayTo(windowEvent));
  }
  return registry;
}

const HANDLERS = buildRegistry();

export function dispatchGlobalEvent(payload: SSEPayload, deps: GlobalEventDeps): void {
  HANDLERS.get(payload.type)?.(payload, deps);
}
