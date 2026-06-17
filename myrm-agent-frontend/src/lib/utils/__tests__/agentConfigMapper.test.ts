import { describe, it, expect } from 'vitest';
import { buildAgentConfig } from '../agentConfigMapper';
import type { Agent } from '@/services/agent';

const makeAgent = (overrides: Partial<Agent> = {}): Agent => ({
  id: 'test-agent',
  user_id: 'user-1',
  name: 'Test Agent',
  description: 'A test agent',
  avatar_url: 'icon:general',
  system_prompt: 'You are helpful.',
  skill_ids: ['skill-a'],
  mcp_ids: ['mcp-b'],
  skill_configs: { 'skill-a': { is_core: true } },
  enabled_builtin_tools: ['web_search', 'code_interpreter'],
  browser_engine: 'puppeteer',
  browser_source: 'built_in',
  dialog_policy: 'smart',
  session_recording: 'on_failure',
  auto_restore_domains: ['github.com'],
  suggestion_prompts: ['Hello', 'Help'],
  memory_decay_profile: 'normal',
  mcp_tool_selections: { 'mcp-b': ['tool1'] },
  model_selection: {
    providerId: 'openai',
    model: 'gpt-4o',
    fallbackProviderId: 'anthropic',
    fallbackModel: 'claude-3-sonnet',
    safetyFallbackProviderId: 'openai',
    safetyFallbackModel: 'gpt-4o-mini',
  },
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
  ...overrides,
});

describe('buildAgentConfig', () => {
  it('maps all core fields', () => {
    const config = buildAgentConfig(makeAgent());

    expect(config.agentId).toBe('test-agent');
    expect(config.agentName).toBe('Test Agent');
    expect(config.agentDescription).toBe('A test agent');
    expect(config.avatarUrl).toBe('icon:general');
    expect(config.systemPrompt).toBe('You are helpful.');
    expect(config.selectedSkillIds).toEqual(['skill-a']);
    expect(config.selectedMcpNames).toEqual(['mcp-b']);
    expect(config.skillConfigs).toEqual({ 'skill-a': { is_core: true } });
    expect(config.useGlobalInstruction).toBe(true);
  });

  it('maps modelSelection correctly', () => {
    const config = buildAgentConfig(makeAgent());

    expect(config.modelSelection).toEqual({ providerId: 'openai', model: 'gpt-4o' });
    expect(config.fallbackModelSelection).toEqual({ providerId: 'anthropic', model: 'claude-3-sonnet' });
    expect(config.safetyFallbackModelSelection).toEqual({ providerId: 'openai', model: 'gpt-4o-mini' });
  });

  it('handles null model_selection', () => {
    const config = buildAgentConfig(makeAgent({ model_selection: null }));

    expect(config.modelSelection).toBeUndefined();
    expect(config.fallbackModelSelection).toBeUndefined();
    expect(config.safetyFallbackModelSelection).toBeUndefined();
  });

  it('handles partial model_selection (no fallback)', () => {
    const config = buildAgentConfig(
      makeAgent({
        model_selection: { providerId: 'openai', model: 'gpt-4o' },
      }),
    );

    expect(config.modelSelection).toEqual({ providerId: 'openai', model: 'gpt-4o' });
    expect(config.fallbackModelSelection).toBeUndefined();
    expect(config.safetyFallbackModelSelection).toBeUndefined();
  });

  it('maps builtin tools and browser config', () => {
    const config = buildAgentConfig(makeAgent());

    expect(config.enabledBuiltinTools).toEqual(['web_search', 'code_interpreter']);
    expect(config.browserEngine).toBe('puppeteer');
    expect(config.browserSource).toBe('built_in');
  });

  it('maps dialog and recording policies', () => {
    const config = buildAgentConfig(makeAgent());

    expect(config.dialogPolicy).toBe('smart');
    expect(config.sessionRecording).toBe('on_failure');
  });

  it('maps memory and mcp tool selections', () => {
    const config = buildAgentConfig(makeAgent());

    expect(config.memoryDecayProfile).toBe('normal');
    expect(config.mcpToolSelections).toEqual({ 'mcp-b': ['tool1'] });
  });

  it('defaults null fields gracefully', () => {
    const config = buildAgentConfig(
      makeAgent({
        system_prompt: undefined,
        skill_ids: undefined,
        mcp_ids: undefined,
        skill_configs: null,
        enabled_builtin_tools: null,
        browser_engine: null,
        auto_restore_domains: null,
        suggestion_prompts: null,
      }),
    );

    expect(config.systemPrompt).toBe('');
    expect(config.selectedSkillIds).toEqual([]);
    expect(config.selectedMcpNames).toEqual([]);
    expect(config.skillConfigs).toEqual({});
    expect(config.enabledBuiltinTools).toBeUndefined();
    expect(config.browserEngine).toBeUndefined();
    expect(config.autoRestoreDomains).toEqual([]);
    expect(config.suggestionPrompts).toBeUndefined();
  });

  it('handles empty arrays for skill_ids and mcp_ids', () => {
    const config = buildAgentConfig(makeAgent({ skill_ids: [], mcp_ids: [] }));

    expect(config.selectedSkillIds).toEqual([]);
    expect(config.selectedMcpNames).toEqual([]);
  });

  it('handles empty mcp_tool_selections object', () => {
    const config = buildAgentConfig(makeAgent({ mcp_tool_selections: {} }));

    expect(config.mcpToolSelections).toEqual({});
  });

  it('handles model_selection with only primary (no fallback or safety)', () => {
    const config = buildAgentConfig(
      makeAgent({
        model_selection: {
          providerId: 'anthropic',
          model: 'claude-4-opus',
        },
      }),
    );

    expect(config.modelSelection).toEqual({ providerId: 'anthropic', model: 'claude-4-opus' });
    expect(config.fallbackModelSelection).toBeUndefined();
    expect(config.safetyFallbackModelSelection).toBeUndefined();
  });

  it('handles model_selection with empty string provider/model', () => {
    const config = buildAgentConfig(
      makeAgent({
        model_selection: { providerId: '', model: '' },
      }),
    );

    expect(config.modelSelection).toBeUndefined();
  });

  it('handles model_selection with only safety fallback (no primary, no fallback)', () => {
    const config = buildAgentConfig(
      makeAgent({
        model_selection: {
          providerId: '',
          model: '',
          safetyFallbackProviderId: 'openai',
          safetyFallbackModel: 'gpt-4o-mini',
        },
      }),
    );

    expect(config.modelSelection).toBeUndefined();
    expect(config.fallbackModelSelection).toBeUndefined();
    expect(config.safetyFallbackModelSelection).toEqual({ providerId: 'openai', model: 'gpt-4o-mini' });
  });

  it('preserves all agent metadata fields', () => {
    const agent = makeAgent({
      id: 'unique-id-123',
      name: 'Custom Agent Name',
      description: 'Custom description with special chars: <>&"',
      avatar_url: 'https://example.com/avatar.png',
    });
    const config = buildAgentConfig(agent);

    expect(config.agentId).toBe('unique-id-123');
    expect(config.agentName).toBe('Custom Agent Name');
    expect(config.agentDescription).toBe('Custom description with special chars: <>&"');
    expect(config.avatarUrl).toBe('https://example.com/avatar.png');
  });

  it('maps all dialog policy variants', () => {
    for (const policy of ['smart', 'always', 'never'] as const) {
      const config = buildAgentConfig(makeAgent({ dialog_policy: policy }));
      expect(config.dialogPolicy).toBe(policy);
    }
  });

  it('maps all session recording variants', () => {
    for (const recording of ['always', 'on_failure', 'never'] as const) {
      const config = buildAgentConfig(makeAgent({ session_recording: recording }));
      expect(config.sessionRecording).toBe(recording);
    }
  });

  it('handles multiple mcp_tool_selections entries', () => {
    const config = buildAgentConfig(
      makeAgent({
        mcp_tool_selections: {
          'mcp-a': ['read', 'write'],
          'mcp-b': ['search'],
          'mcp-c': [],
        },
      }),
    );

    expect(config.mcpToolSelections).toEqual({
      'mcp-a': ['read', 'write'],
      'mcp-b': ['search'],
      'mcp-c': [],
    });
  });
});
