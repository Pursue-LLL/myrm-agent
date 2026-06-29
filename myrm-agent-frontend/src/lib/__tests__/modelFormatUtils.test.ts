import { describe, expect, it } from 'vitest';

import { formatTokens, formatPrice } from '@/lib/utils/modelFormatUtils';

describe('formatTokens', () => {
  it('returns empty string for undefined', () => {
    expect(formatTokens(undefined)).toBe('');
  });

  it('returns empty string for 0', () => {
    expect(formatTokens(0)).toBe('');
  });

  it('formats millions', () => {
    expect(formatTokens(1_000_000)).toBe('1M');
    expect(formatTokens(2_000_000)).toBe('2M');
  });

  it('formats thousands', () => {
    expect(formatTokens(128_000)).toBe('128K');
    expect(formatTokens(200_000)).toBe('200K');
    expect(formatTokens(1_000)).toBe('1K');
  });

  it('formats small values as-is', () => {
    expect(formatTokens(512)).toBe('512');
  });
});

describe('formatPrice', () => {
  it('returns dash for null/undefined', () => {
    expect(formatPrice(undefined)).toBe('-');
    expect(formatPrice(null as unknown as undefined)).toBe('-');
  });

  it('returns $0/M for zero', () => {
    expect(formatPrice(0)).toBe('$0/M');
  });

  it('formats very small prices with 4 decimals', () => {
    expect(formatPrice(0.0005)).toBe('$0.0005/M');
  });

  it('formats small prices with 3 decimals', () => {
    expect(formatPrice(0.005)).toBe('$0.005/M');
  });

  it('formats sub-dollar prices with 2 decimals', () => {
    expect(formatPrice(0.15)).toBe('$0.15/M');
    expect(formatPrice(0.50)).toBe('$0.50/M');
  });

  it('formats single-digit prices with 1 decimal', () => {
    expect(formatPrice(3.0)).toBe('$3.0/M');
    expect(formatPrice(5.5)).toBe('$5.5/M');
  });

  it('formats large prices as integers', () => {
    expect(formatPrice(15)).toBe('$15/M');
    expect(formatPrice(60)).toBe('$60/M');
  });
});

describe('cost data source unification (per_token → per_million)', () => {
  it('converts LiteLLM per_token price to per_million correctly', () => {
    const perToken = 0.000003;
    const perMillion = perToken * 1_000_000;
    expect(perMillion).toBe(3);
    expect(formatPrice(perMillion)).toBe('$3.0/M');
  });

  it('handles Claude 3.5 Sonnet pricing correctly', () => {
    const inputPerToken = 0.000003;
    const outputPerToken = 0.000015;
    expect(formatPrice(inputPerToken * 1_000_000)).toBe('$3.0/M');
    expect(formatPrice(outputPerToken * 1_000_000)).toBe('$15/M');
  });

  it('handles GPT-4o pricing correctly', () => {
    const inputPerToken = 0.0000025;
    const outputPerToken = 0.00001;
    expect(formatPrice(inputPerToken * 1_000_000)).toBe('$2.5/M');
    expect(formatPrice(outputPerToken * 1_000_000)).toBe('$10/M');
  });

  it('handles free model (zero cost) correctly', () => {
    const perToken = 0;
    const perMillion = perToken * 1_000_000;
    expect(perMillion).toBe(0);
    expect(formatPrice(perMillion)).toBe('$0/M');
  });

  it('handles very cheap models (DeepSeek) correctly', () => {
    const inputPerToken = 0.00000014;
    const perMillion = inputPerToken * 1_000_000;
    expect(formatPrice(perMillion)).toBe('$0.14/M');
  });
});

describe('contextLabel derivation edge cases', () => {
  it('null max_input_tokens produces no badge', () => {
    const caps = { max_input_tokens: null };
    const contextLabel = caps.max_input_tokens ? formatTokens(caps.max_input_tokens) : null;
    expect(contextLabel).toBeNull();
  });

  it('0 max_input_tokens produces no badge', () => {
    const caps = { max_input_tokens: 0 };
    const contextLabel = caps.max_input_tokens ? formatTokens(caps.max_input_tokens) : null;
    expect(contextLabel).toBeNull();
  });

  it('undefined max_input_tokens produces no badge', () => {
    const caps = { max_input_tokens: undefined };
    const contextLabel = caps.max_input_tokens ? formatTokens(caps.max_input_tokens) : null;
    expect(contextLabel).toBeNull();
  });

  it('valid max_input_tokens produces correct badge', () => {
    expect(formatTokens(128_000)).toBe('128K');
    expect(formatTokens(200_000)).toBe('200K');
    expect(formatTokens(1_000_000)).toBe('1M');
    expect(formatTokens(2_000_000)).toBe('2M');
  });
});
