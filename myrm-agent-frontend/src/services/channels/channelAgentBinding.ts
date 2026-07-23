/**
 * Channel bindable agent filter — Settings/IM dropdown SSOT (client-side defense-in-depth).
 *
 * [INPUT]
 * - services/agent::AgentListItem (POS: user-agents list DTO)
 * - Server SqlTopicManager.bind_topic (POS: write gate rejects prompt_mode=search)
 *
 * [OUTPUT]
 * - filterChannelBindableAgents: General-only agent list for channel routing UI
 *
 * [POS]
 * Client mirror of Channel bind policy. Blocks builtin Search presets by ID and any
 * agent with prompt_mode=search. Server remains SSOT for bind rejection and read sanitize.
 */

import type { AgentListItem } from '@/services/agent';

/** Built-in Search presets — Web fast-mode only, never Channel bind targets. */
const CHANNEL_BLOCKED_SEARCH_AGENT_IDS = new Set([
  'builtin-fast-search',
  'builtin-deep-search',
]);

function isChannelBindableAgent(agent: AgentListItem): boolean {
  if (CHANNEL_BLOCKED_SEARCH_AGENT_IDS.has(agent.id)) {
    return false;
  }
  return agent.prompt_mode !== 'search';
}

/** General agents only — Search preset agents (`prompt_mode=search`) are Web fast-mode only. */
export function filterChannelBindableAgents(agents: AgentListItem[]): AgentListItem[] {
  return agents.filter(isChannelBindableAgent);
}
