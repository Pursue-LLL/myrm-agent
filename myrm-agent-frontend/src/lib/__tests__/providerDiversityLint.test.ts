import { describe, it, expect } from 'vitest';
import { extractRootVendor, validateProviderDiversity } from '../providerDiversityLint';

describe('extractRootVendor', () => {
  it('extracts direct provider vendors', () => {
    expect(extractRootVendor('openai', 'gpt-4o')).toBe('openai');
    expect(extractRootVendor('azure-openai', 'gpt-4o-mini')).toBe('openai');
    expect(extractRootVendor('anthropic', 'claude-3-5-sonnet')).toBe('anthropic');
    expect(extractRootVendor('deepseek', 'deepseek-chat')).toBe('deepseek');
    expect(extractRootVendor('google', 'gemini-1.5-pro')).toBe('google');
    expect(extractRootVendor('qwen', 'qwen-2.5-72b')).toBe('qwen');
    expect(extractRootVendor('xai', 'grok-2')).toBe('xai');
  });

  it('extracts vendor from openrouter and proxy model prefixes', () => {
    expect(extractRootVendor('openrouter', 'meta-llama/llama-3.3-70b-instruct')).toBe('meta');
    expect(extractRootVendor('openrouter', 'qwen/qwen-2.5-coder-32b-instruct')).toBe('qwen');
    expect(extractRootVendor('openrouter', 'anthropic/claude-3-5-sonnet')).toBe('anthropic');
    expect(extractRootVendor('openrouter', 'deepseek/deepseek-chat')).toBe('deepseek');
  });

  it('uses model heuristics when provider is empty', () => {
    expect(extractRootVendor('', 'gpt-4o')).toBe('openai');
    expect(extractRootVendor('', 'claude-3-5-haiku')).toBe('anthropic');
    expect(extractRootVendor('', 'deepseek-coder')).toBe('deepseek');
    expect(extractRootVendor('', 'llama-3.1-8b')).toBe('meta');
    expect(extractRootVendor('', 'qwen-2.5-14b')).toBe('qwen');
  });
});

describe('validateProviderDiversity', () => {
  it('fails on empty selections', () => {
    const res = validateProviderDiversity([]);
    expect(res.isValid).toBe(false);
    expect(res.distinctVendorCount).toBe(0);
  });

  it('fails on single vendor selections', () => {
    const selections = [
      { providerId: 'openai', model: 'gpt-4o' },
      { providerId: 'azure-openai', model: 'gpt-4o-mini' },
      { providerId: 'openai', model: 'o1' },
    ];
    const res = validateProviderDiversity(selections, 2);
    expect(res.isValid).toBe(false);
    expect(res.distinctVendorCount).toBe(1);
    expect(res.distinctVendors).toEqual(['openai']);
  });

  it('passes on heterogeneous multi-vendor selections', () => {
    const selections = [
      { providerId: 'deepseek', model: 'deepseek-chat' },
      { providerId: 'anthropic', model: 'claude-3-5-sonnet-20241022' },
      { providerId: 'openrouter', model: 'meta-llama/llama-3.3-70b-instruct' },
    ];
    const res = validateProviderDiversity(selections, 2);
    expect(res.isValid).toBe(true);
    expect(res.distinctVendorCount).toBe(3);
    expect(res.distinctVendors).toEqual(['anthropic', 'deepseek', 'meta']);
    expect(res.slotsEvaluated).toBe(3);
  });
});
