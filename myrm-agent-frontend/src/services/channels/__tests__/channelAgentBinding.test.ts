import { describe, expect, it } from 'vitest';
import type { AgentListItem } from '@/services/agent';
import { filterChannelBindableAgents } from '@/services/channels/channelAgentBinding';

function agent(id: string, promptMode?: string): AgentListItem {
  return {
    id,
    name: id,
    prompt_mode: promptMode,
    created_at: '',
    updated_at: '',
  };
}

describe('filterChannelBindableAgents', () => {
  it('excludes search agents from channel binding options', () => {
    const agents = [agent('general-1', 'full'), agent('builtin-fast-search', 'search')];
    expect(filterChannelBindableAgents(agents).map((a) => a.id)).toEqual(['general-1']);
  });

  it('excludes builtin search presets when list API omits prompt_mode', () => {
    const agents = [agent('general-1'), agent('builtin-fast-search')];
    expect(filterChannelBindableAgents(agents).map((a) => a.id)).toEqual(['general-1']);
  });

  it('excludes builtin-deep-search preset', () => {
    const agents = [agent('general-1', 'full'), agent('builtin-deep-search', 'search')];
    expect(filterChannelBindableAgents(agents).map((a) => a.id)).toEqual(['general-1']);
  });

  it('excludes custom agents with prompt_mode search', () => {
    const agents = [agent('general-1', 'full'), agent('custom-search', 'search')];
    expect(filterChannelBindableAgents(agents).map((a) => a.id)).toEqual(['general-1']);
  });
});
