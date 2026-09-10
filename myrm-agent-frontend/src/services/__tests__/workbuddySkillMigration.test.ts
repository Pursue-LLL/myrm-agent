import { describe, it, expect } from 'vitest';
import {
  WORKBUDDY_TOP_20_MIGRATION_MAP,
  resolveMyrmSkillFromWorkbuddy,
  searchWorkbuddyMigrationSkills,
} from '../workbuddySkillMigration';

describe('workbuddySkillMigration', () => {
  it('should define exactly 20 essential skill mappings', () => {
    expect(WORKBUDDY_TOP_20_MIGRATION_MAP).toHaveLength(20);
  });

  it('should ensure all mapping items have valid categories and ids', () => {
    const validCategories = new Set(['office', 'engineering', 'growth', 'operations']);
    const ids = new Set<string>();

    WORKBUDDY_TOP_20_MIGRATION_MAP.forEach((item) => {
      expect(validCategories.has(item.category)).toBe(true);
      expect(item.id).toMatch(/^wb-[a-z0-9-]+$/);
      expect(item.myrmSkillId).toBeTruthy();
      expect(item.wbNameZh).toBeTruthy();
      expect(item.wbNameEn).toBeTruthy();
      expect(item.recommendedPromptZh).toBeTruthy();
      expect(item.recommendedPromptEn).toBeTruthy();
      expect(ids.has(item.id)).toBe(false);
      ids.add(item.id);
    });
  });

  it('should resolve Myrm skill by exact wb id', () => {
    const result = resolveMyrmSkillFromWorkbuddy('wb-weekly-report');
    expect(result).not.toBeNull();
    expect(result?.myrmSkillId).toBe('daily-briefing');
    expect(result?.wbNameZh).toBe('周报生成器');
  });

  it('should resolve Myrm skill by Chinese name keyword', () => {
    const result = resolveMyrmSkillFromWorkbuddy('竞品情报');
    expect(result).not.toBeNull();
    expect(result?.myrmSkillId).toBe('competitive-analysis-pipeline');
  });

  it('should resolve Myrm skill by English name keyword', () => {
    const result = resolveMyrmSkillFromWorkbuddy('Host Server Ops');
    expect(result).not.toBeNull();
    expect(result?.myrmSkillId).toBe('host-server-ops');
  });

  it('should search skills across fields', () => {
    const results = searchWorkbuddyMigrationSkills('架构');
    expect(results.length).toBeGreaterThan(0);
    expect(results.some((r) => r.myrmSkillId === 'architecture-diagram')).toBe(true);
  });

  it('should return all skills when query is empty', () => {
    const results = searchWorkbuddyMigrationSkills('   ');
    expect(results).toHaveLength(20);
  });
});
