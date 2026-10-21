import { describe, expect, it } from 'vitest';
import { isModelAllowedByPolicy } from '../org-model-policy';
import { getLiteLLMModelName } from '@/store/config/providerTypes';

describe('isModelAllowedByPolicy', () => {
  it('allows all models when patterns list is empty', () => {
    expect(isModelAllowedByPolicy('any-model', [])).toBe(true);
  });

  it('matches exact pattern', () => {
    expect(isModelAllowedByPolicy('gpt-4o', ['gpt-4o'])).toBe(true);
    expect(isModelAllowedByPolicy('gpt-4', ['gpt-4o'])).toBe(false);
  });

  it('matches wildcard suffix', () => {
    expect(isModelAllowedByPolicy('deepseek-chat', ['deepseek-*'])).toBe(true);
    expect(isModelAllowedByPolicy('deepseek-coder-v3', ['deepseek-*'])).toBe(true);
    expect(isModelAllowedByPolicy('qwen-chat', ['deepseek-*'])).toBe(false);
  });

  it('matches wildcard prefix', () => {
    expect(isModelAllowedByPolicy('openai/gpt-4o', ['*/gpt-4o'])).toBe(true);
    expect(isModelAllowedByPolicy('azure/gpt-4o', ['*/gpt-4o'])).toBe(true);
  });

  it('matches universal wildcard', () => {
    expect(isModelAllowedByPolicy('anything', ['*'])).toBe(true);
  });

  it('matches with question mark single char', () => {
    expect(isModelAllowedByPolicy('gpt-4o', ['gpt-?o'])).toBe(true);
    expect(isModelAllowedByPolicy('gpt-40', ['gpt-?o'])).toBe(false);
  });

  it('matches any pattern in list', () => {
    const patterns = ['deepseek-*', 'claude-*', 'qwen-*'];
    expect(isModelAllowedByPolicy('claude-3.5-sonnet', patterns)).toBe(true);
    expect(isModelAllowedByPolicy('gpt-4o', patterns)).toBe(false);
  });

  it('escapes regex special chars in patterns', () => {
    expect(isModelAllowedByPolicy('openai/gpt-4.0', ['openai/gpt-4.0'])).toBe(true);
    expect(isModelAllowedByPolicy('openai/gpt-4X0', ['openai/gpt-4.0'])).toBe(false);
  });
});

describe('model-picker integration: getLiteLLMModelName + isModelAllowedByPolicy', () => {
  const patterns = ['openai/*', 'deepseek/*'];

  it('allows openai model via LiteLLM format conversion', () => {
    const litellmName = getLiteLLMModelName('openai', 'gpt-4o-mini');
    expect(litellmName).toBe('openai/gpt-4o-mini');
    expect(isModelAllowedByPolicy(litellmName, patterns)).toBe(true);
  });

  it('allows deepseek model via LiteLLM format conversion', () => {
    const litellmName = getLiteLLMModelName('deepseek', 'deepseek-chat');
    expect(litellmName).toBe('deepseek/deepseek-chat');
    expect(isModelAllowedByPolicy(litellmName, patterns)).toBe(true);
  });

  it('blocks anthropic model via LiteLLM format conversion', () => {
    const litellmName = getLiteLLMModelName('anthropic', 'claude-4-opus');
    expect(litellmName).toBe('anthropic/claude-4-opus');
    expect(isModelAllowedByPolicy(litellmName, patterns)).toBe(false);
  });

  it('raw model name without conversion would give wrong result', () => {
    expect(isModelAllowedByPolicy('gpt-4o-mini', patterns)).toBe(false);
    const litellmName = getLiteLLMModelName('openai', 'gpt-4o-mini');
    expect(isModelAllowedByPolicy(litellmName, patterns)).toBe(true);
  });

  it('model already in LiteLLM format is not double-prefixed', () => {
    const litellmName = getLiteLLMModelName('openai', 'openai/gpt-4o');
    expect(litellmName).toBe('openai/gpt-4o');
    expect(isModelAllowedByPolicy(litellmName, patterns)).toBe(true);
  });
});
