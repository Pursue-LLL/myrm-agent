import { describe, expect, it } from 'vitest';
import { isModelAllowedByPolicy } from '../org-model-policy';

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
