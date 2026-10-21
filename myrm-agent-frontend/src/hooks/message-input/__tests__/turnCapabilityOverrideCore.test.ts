import { describe, expect, it } from 'vitest';
import type { AgentConfig } from '@/store/chat/types';
import {
  buildTurnAgentConfigOverride,
  normalizeTurnCapabilitySelection,
  resolveEffectiveTurnSelection,
} from '@/hooks/message-input/turnCapabilityOverrideCore';

const BASE_CONFIG: AgentConfig = {
  selectedSkillIds: ['skill-a', 'skill-b'],
  selectedMcpNames: ['mcp-a', 'mcp-b'],
  systemPrompt: '',
  useGlobalInstruction: true,
};

describe('turnCapabilityOverrideCore', () => {
  it('resolves effective selection in base order and drops unknown items', () => {
    const resolved = resolveEffectiveTurnSelection(['a', 'b', 'c'], ['c', 'x', 'a']);
    expect(resolved).toEqual(['a', 'c']);
  });

  it('normalizes no-op selection to null', () => {
    const normalized = normalizeTurnCapabilitySelection(
      ['skill-a', 'skill-b'],
      ['mcp-a', 'mcp-b'],
      ['skill-a', 'skill-b'],
      ['mcp-a', 'mcp-b'],
    );
    expect(normalized).toBeNull();
  });

  it('keeps explicit empty subset for one-turn disable', () => {
    const normalized = normalizeTurnCapabilitySelection(['skill-a', 'skill-b'], ['mcp-a'], [], null);
    expect(normalized).toEqual({
      skillIds: [],
      mcpNames: null,
    });
  });

  it('falls back to defaults when stale selected ids no longer exist', () => {
    const normalized = normalizeTurnCapabilitySelection(['skill-a', 'skill-b'], ['mcp-a'], ['legacy-skill'], null);
    expect(normalized).toBeNull();
  });

  it('builds one-turn override from normalized subset', () => {
    const override = buildTurnAgentConfigOverride(BASE_CONFIG, {
      skillIds: ['skill-b', 'unknown'],
      mcpNames: null,
    });
    expect(override).toMatchObject({
      selectedSkillIds: ['skill-b'],
      selectedMcpNames: ['mcp-a', 'mcp-b'],
    });
  });

  it('returns null when selection does not change effective config', () => {
    const override = buildTurnAgentConfigOverride(BASE_CONFIG, {
      skillIds: ['skill-a', 'skill-b'],
      mcpNames: ['mcp-a', 'mcp-b'],
    });
    expect(override).toBeNull();
  });
});
