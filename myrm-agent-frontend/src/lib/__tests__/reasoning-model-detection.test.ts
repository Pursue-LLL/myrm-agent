import { describe, expect, it } from 'vitest';
import { isReasoningModelByName, detectReasoningSupport } from '@/lib/reasoning-model-detection';

describe('isReasoningModelByName', () => {
  it('should return false for empty string', () => {
    expect(isReasoningModelByName('')).toBe(false);
  });

  it('should detect Anthropic Claude reasoning models', () => {
    expect(isReasoningModelByName('claude-3-7-sonnet-20250514')).toBe(true);
    expect(isReasoningModelByName('claude-3.7-sonnet')).toBe(true);
    expect(isReasoningModelByName('claude-sonnet-4-20250514')).toBe(true);
    expect(isReasoningModelByName('claude-opus-4-20250514')).toBe(true);
    expect(isReasoningModelByName('claude-haiku-4-20250514')).toBe(true);
  });

  it('should detect OpenAI reasoning models', () => {
    expect(isReasoningModelByName('o1')).toBe(true);
    expect(isReasoningModelByName('o1-mini')).toBe(true);
    expect(isReasoningModelByName('o1-preview')).toBe(true);
    expect(isReasoningModelByName('o3')).toBe(true);
    expect(isReasoningModelByName('o3-mini')).toBe(true);
    expect(isReasoningModelByName('o4-mini')).toBe(true);
    expect(isReasoningModelByName('gpt-5')).toBe(true);
    expect(isReasoningModelByName('gpt-5-turbo')).toBe(true);
  });

  it('should detect Google Gemini reasoning models', () => {
    expect(isReasoningModelByName('gemini-2.5-flash')).toBe(true);
    expect(isReasoningModelByName('gemini-2.5-pro')).toBe(true);
    expect(isReasoningModelByName('gemini-thinking')).toBe(true);
  });

  it('should detect DeepSeek reasoning models', () => {
    expect(isReasoningModelByName('deepseek-r1')).toBe(true);
    expect(isReasoningModelByName('deepseek-v3')).toBe(true);
    expect(isReasoningModelByName('deepseek-chat-v3')).toBe(true);
  });

  it('should detect Qwen reasoning models', () => {
    expect(isReasoningModelByName('qwen3-235b-a22b')).toBe(true);
    expect(isReasoningModelByName('qwq-72b')).toBe(true);
    expect(isReasoningModelByName('qvq-72b')).toBe(true);
  });

  it('should detect other reasoning models', () => {
    expect(isReasoningModelByName('grok-3')).toBe(true);
    expect(isReasoningModelByName('grok-4')).toBe(true);
    expect(isReasoningModelByName('magistral')).toBe(true);
    expect(isReasoningModelByName('kimi-k2-thinking')).toBe(true);
    expect(isReasoningModelByName('minimax-m1')).toBe(true);
    expect(isReasoningModelByName('mimo')).toBe(true);
    expect(isReasoningModelByName('step-3')).toBe(true);
    expect(isReasoningModelByName('glm-z1')).toBe(true);
    expect(isReasoningModelByName('baichuan-m2')).toBe(true);
    expect(isReasoningModelByName('ring-1t')).toBe(true);
  });

  it('should not detect non-reasoning models', () => {
    expect(isReasoningModelByName('gpt-4o')).toBe(false);
    expect(isReasoningModelByName('gpt-4o-mini')).toBe(false);
    expect(isReasoningModelByName('claude-3-5-sonnet')).toBe(false);
    expect(isReasoningModelByName('claude-3-5-haiku')).toBe(false);
    expect(isReasoningModelByName('gemini-2.0-flash')).toBe(false);
    expect(isReasoningModelByName('deepseek-chat')).toBe(false);
    expect(isReasoningModelByName('qwen-72b')).toBe(false);
  });

  it('should be case-insensitive', () => {
    expect(isReasoningModelByName('CLAUDE-3-7-SONNET')).toBe(true);
    expect(isReasoningModelByName('O3-MINI')).toBe(true);
    expect(isReasoningModelByName('GEMINI-2.5-FLASH')).toBe(true);
  });

  it('should handle model IDs with provider prefix', () => {
    expect(isReasoningModelByName('anthropic/claude-3-7-sonnet')).toBe(true);
    expect(isReasoningModelByName('openai/o3-mini')).toBe(true);
    expect(isReasoningModelByName('google/gemini-2.5-flash')).toBe(true);
    expect(isReasoningModelByName('deepseek/deepseek-r1')).toBe(true);
  });

  it('should handle model IDs with version numbers', () => {
    expect(isReasoningModelByName('claude-3-7-sonnet-20250514')).toBe(true);
    expect(isReasoningModelByName('o3-mini-2025-01')).toBe(true);
    expect(isReasoningModelByName('gemini-2.5-flash-preview')).toBe(true);
  });

  it('should not match partial model names', () => {
    expect(isReasoningModelByName('gpt-4o-reasoning')).toBe(false);
    expect(isReasoningModelByName('claude-3-5-sonnet-thinking')).toBe(false);
    expect(isReasoningModelByName('gemini-2.0-flash-reasoning')).toBe(false);
  });
});

describe('detectReasoningSupport', () => {
  it('should use API value when provided', () => {
    expect(detectReasoningSupport('gpt-4o', true)).toBe(true);
    expect(detectReasoningSupport('gpt-4o', false)).toBe(false);
    expect(detectReasoningSupport('claude-3-7-sonnet', true)).toBe(true);
    expect(detectReasoningSupport('claude-3-7-sonnet', false)).toBe(false);
  });

  it('should fallback to regex when API value is undefined', () => {
    expect(detectReasoningSupport('claude-3-7-sonnet', undefined)).toBe(true);
    expect(detectReasoningSupport('gpt-4o', undefined)).toBe(false);
    expect(detectReasoningSupport('o3-mini', undefined)).toBe(true);
    expect(detectReasoningSupport('gemini-2.5-flash', undefined)).toBe(true);
  });

  it('should return false for empty model id', () => {
    expect(detectReasoningSupport('', undefined)).toBe(false);
    expect(detectReasoningSupport('', true)).toBe(true);
    expect(detectReasoningSupport('', false)).toBe(false);
  });
});
