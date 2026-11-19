/**
 * Which turns need a configured search service: the fast search mode, and the Quick Search agent picked in agent mode.
 * The answer follows the agent identity a request is sent under, so it must agree with `resolveEffectiveAgentId`.
 */
import { describe, expect, it } from 'vitest';
import { resolveEffectiveAgentId } from '@/store/chat/messageRequest';
import { FAST_SEARCH_AGENT_ID, requiresSearchService } from '@/store/chat/searchRequirement';
import type { ActionMode, AgentConfig } from '@/store/chat/types';

const agent = (agentId?: string): AgentConfig => ({
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: true,
  agentId,
});

const CASES: ReadonlyArray<readonly [label: string, mode: ActionMode, config: AgentConfig | null, needed: boolean]> = [
  ['fast mode', 'fast', null, true],
  ['fast mode whatever the agent config holds', 'fast', agent('builtin-general'), true],
  ['the Quick Search agent in agent mode', 'agent', agent(FAST_SEARCH_AGENT_ID), true],
  ['the Quick Search agent with stray whitespace', 'agent', agent(` ${FAST_SEARCH_AGENT_ID} `), true],
  ['the general agent', 'agent', agent('builtin-general'), false],
  ['a hidden search agent, which resolves to the general agent', 'agent', agent('builtin-deep-search'), false],
  ['an agent config without an agent id', 'agent', agent(), false],
  ['no agent config', 'agent', null, false],
];

describe('requiresSearchService', () => {
  it.each(CASES)('%s', (_label, mode, config, needed) => {
    expect(requiresSearchService(mode, config)).toBe(needed);
  });

  it.each(CASES)('agrees with the agent identity a request is sent under: %s', (_label, mode, config) => {
    expect(requiresSearchService(mode, config)).toBe(resolveEffectiveAgentId(mode, config) === FAST_SEARCH_AGENT_ID);
  });
});
