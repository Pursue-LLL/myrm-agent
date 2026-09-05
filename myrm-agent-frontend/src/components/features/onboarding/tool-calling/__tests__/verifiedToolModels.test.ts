import { describe, it, expect } from 'vitest';
import { isVerifiedToolCallingModel, VERIFIED_TOOL_MODELS } from '../verifiedToolModels';

describe('verifiedToolModels', () => {
  it('contains expected benchmark models', () => {
    const ids = VERIFIED_TOOL_MODELS.map((m) => m.id);
    expect(ids).toContain('claude-3-5-sonnet-latest');
    expect(ids).toContain('gpt-4o');
    expect(ids).toContain('deepseek-chat');
    expect(ids).toContain('qwen-2.5-coder-32b-instruct');
  });

  it('correctly validates official verified model strings', () => {
    expect(isVerifiedToolCallingModel('claude-3-5-sonnet-20241022')).toBe(true);
    expect(isVerifiedToolCallingModel('gpt-4o-mini')).toBe(true);
    expect(isVerifiedToolCallingModel('deepseek-chat')).toBe(true);
    expect(isVerifiedToolCallingModel('qwen2.5-coder:32b')).toBe(true);
  });

  it('correctly marks unverified or pure-chat models as false', () => {
    expect(isVerifiedToolCallingModel('llama-3-8b-instruct')).toBe(false);
    expect(isVerifiedToolCallingModel('random-custom-model-v1')).toBe(false);
    expect(isVerifiedToolCallingModel('')).toBe(false);
  });
});
