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
});
