import { describe, it, expect } from 'vitest';
import { resolveSkillDescription } from '../skillUtils';

describe('skillUtils - resolveSkillDescription', () => {
  it('returns skill description if present and non-empty', () => {
    expect(resolveSkillDescription({ description: 'A helpful skill' }, 'No description')).toBe(
      'A helpful skill'
    );
  });

  it('returns fallback when description is missing, null or empty whitespace', () => {
    expect(resolveSkillDescription({ description: '' }, '暂无描述')).toBe('暂无描述');
    expect(resolveSkillDescription({ description: '   ' }, '暂无描述')).toBe('暂无描述');
    expect(resolveSkillDescription(null, '暂无描述')).toBe('暂无描述');
    expect(resolveSkillDescription(undefined, '暂无描述')).toBe('暂无描述');
  });
});
