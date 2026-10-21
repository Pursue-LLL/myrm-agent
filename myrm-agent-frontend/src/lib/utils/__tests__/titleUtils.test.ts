import { describe, it, expect } from 'vitest';
import { parseTitleIndex, disambiguateChatTitle } from '../titleUtils';

describe('titleUtils - parseTitleIndex & disambiguateChatTitle', () => {
  it('parses base and index correctly', () => {
    expect(parseTitleIndex('方案讨论')).toEqual({ base: '方案讨论', index: 1 });
    expect(parseTitleIndex('方案讨论 (2)')).toEqual({ base: '方案讨论', index: 2 });
    expect(parseTitleIndex('方案讨论 (10)')).toEqual({ base: '方案讨论', index: 10 });
  });

  it('returns candidate title when no collision exists', () => {
    expect(disambiguateChatTitle('方案讨论', ['其他会话', '历史记录'])).toBe('方案讨论');
  });

  it('increments index cleanly when collision exists', () => {
    expect(disambiguateChatTitle('方案讨论', ['方案讨论'])).toBe('方案讨论 (2)');
    expect(disambiguateChatTitle('方案讨论', ['方案讨论', '方案讨论 (2)'])).toBe('方案讨论 (3)');
    expect(disambiguateChatTitle('方案讨论 (2)', ['方案讨论', '方案讨论 (2)'])).toBe('方案讨论 (3)');
  });
});
