import { describe, expect, it } from 'vitest';
import { extractClientRootVendor, validateClientProviderDiversity } from '../paretoProfileLint';

describe('paretoProfileLint', () => {
  describe('extractClientRootVendor', () => {
    it('resolves direct provider mapping', () => {
      expect(extractClientRootVendor('openai', 'gpt-4o')).toBe('openai');
      expect(extractClientRootVendor('azure-openai', 'gpt-4o-mini')).toBe('openai');
      expect(extractClientRootVendor('anthropic', 'claude-3-5-sonnet')).toBe('anthropic');
      expect(extractClientRootVendor('deepseek', 'deepseek-chat')).toBe('deepseek');
      expect(extractClientRootVendor('google', 'gemini-1.5-pro')).toBe('google');
      expect(extractClientRootVendor('qwen', 'qwen-2.5-72b')).toBe('qwen');
    });

    it('resolves OpenRouter prefixes', () => {
      expect(extractClientRootVendor('openrouter', 'meta-llama/llama-3.3-70b-instruct')).toBe('meta');
      expect(extractClientRootVendor('openrouter', 'qwen/qwen-2.5-coder-32b-instruct')).toBe('qwen');
      expect(extractClientRootVendor('openrouter', 'anthropic/claude-3-5-sonnet')).toBe('anthropic');
      expect(extractClientRootVendor('openrouter', 'deepseek/deepseek-chat')).toBe('deepseek');
    });

    it('resolves model name heuristics if provider is empty', () => {
      expect(extractClientRootVendor('', 'gpt-4o')).toBe('openai');
      expect(extractClientRootVendor('', 'claude-3-5-haiku')).toBe('anthropic');
      expect(extractClientRootVendor('', 'deepseek-coder')).toBe('deepseek');
      expect(extractClientRootVendor('', 'meta-llama-3.1-8b')).toBe('meta');
    });
  });

  describe('validateClientProviderDiversity', () => {
    it('fails on empty slots', () => {
      const res = validateClientProviderDiversity([]);
      expect(res.isValid).toBe(false);
      expect(res.distinctVendorCount).toBe(0);
    });

    it('fails when all slots map to the same vendor', () => {
      const slots = [
        { providerId: 'openai', model: 'gpt-4o' },
        { providerId: 'azure-openai', model: 'gpt-4o-mini' },
      ];
      const res = validateClientProviderDiversity(slots, { minDistinctVendors: 2 });
      expect(res.isValid).toBe(false);
      expect(res.distinctVendorCount).toBe(1);
      expect(res.distinctVendors).toEqual(['openai']);
    });

    it('passes when slots span multiple distinct vendors', () => {
      const slots = [
        { providerId: 'deepseek', model: 'deepseek-chat' },
        { providerId: 'anthropic', model: 'claude-3-5-sonnet' },
        { providerId: 'openrouter', model: 'meta-llama/llama-3.3-70b-instruct' },
      ];
      const res = validateClientProviderDiversity(slots, { minDistinctVendors: 2 });
      expect(res.isValid).toBe(true);
      expect(res.distinctVendorCount).toBe(3);
      expect(new Set(res.distinctVendors)).toEqual(new Set(['deepseek', 'anthropic', 'meta']));
    });
  });
});
