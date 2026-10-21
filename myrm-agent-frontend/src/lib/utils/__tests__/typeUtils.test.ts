import { describe, it, expect } from 'vitest';
import { isRecord, asRecord, safeGet } from '../typeUtils';

describe('typeUtils - isRecord, asRecord & safeGet', () => {
  it('identifies plain records safely', () => {
    expect(isRecord({ a: 1 })).toBe(true);
    expect(isRecord(null)).toBe(false);
    expect(isRecord([1, 2, 3])).toBe(false);
    expect(isRecord('string')).toBe(false);
  });

  it('asRecord returns valid record or empty object', () => {
    expect(asRecord({ key: 'value' })).toEqual({ key: 'value' });
    expect(asRecord(null)).toEqual({});
    expect(asRecord('dirty')).toEqual({});
    expect(asRecord(undefined)).toEqual({});
  });

  it('safeGet safely retrieves nested attributes without crashing', () => {
    const complex = {
      metadata: {
        usage: {
          total_tokens: 1500,
        },
      },
    };
    expect(safeGet(complex, 'metadata.usage.total_tokens')).toBe(1500);
    expect(safeGet(complex, 'metadata.invalid.field', 'default')).toBe('default');
    expect(safeGet(null, 'any.path', 'fallback')).toBe('fallback');
  });
});
