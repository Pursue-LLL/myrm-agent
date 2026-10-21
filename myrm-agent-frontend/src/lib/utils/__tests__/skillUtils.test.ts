import { describe, it, expect } from 'vitest';
import { matchesSkillSearch, resolveSkillDescription, type SkillSearchFields } from '../skillUtils';

describe('skillUtils - resolveSkillDescription', () => {
  it('returns skill description if present and non-empty', () => {
    expect(resolveSkillDescription({ description: 'A helpful skill' }, 'No description')).toBe('A helpful skill');
  });

  it('returns fallback when description is missing, null or empty whitespace', () => {
    expect(resolveSkillDescription({ description: '' }, '暂无描述')).toBe('暂无描述');
    expect(resolveSkillDescription({ description: '   ' }, '暂无描述')).toBe('暂无描述');
    expect(resolveSkillDescription(null, '暂无描述')).toBe('暂无描述');
    expect(resolveSkillDescription(undefined, '暂无描述')).toBe('暂无描述');
  });
});

describe('skillUtils - matchesSkillSearch', () => {
  const skill: SkillSearchFields = {
    name: 'Report Writer',
    description: 'Drafts the weekly status report',
    tags: ['Writing', 'weekly'],
    storage_path: '/Users/me/.myrm/skills/report-digest',
  };

  it('matches name, description and tags regardless of case', () => {
    expect(matchesSkillSearch(skill, 'report writer')).toBe(true);
    expect(matchesSkillSearch(skill, 'STATUS')).toBe(true);
    expect(matchesSkillSearch(skill, 'writing')).toBe(true);
  });

  it('matches the folder name even when it differs from the declared name', () => {
    expect(matchesSkillSearch(skill, 'report-digest')).toBe(true);
    expect(
      matchesSkillSearch({ ...skill, storage_path: 'C:\\Users\\me\\skills\\report-digest\\' }, 'report-digest'),
    ).toBe(true);
  });

  it('does not let parent directories make every skill match', () => {
    expect(matchesSkillSearch(skill, 'myrm')).toBe(false);
    expect(matchesSkillSearch(skill, 'users')).toBe(false);
  });

  it('rejects a query found in no field', () => {
    expect(matchesSkillSearch(skill, 'calendar')).toBe(false);
  });
});
