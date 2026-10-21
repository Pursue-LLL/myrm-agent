import { describe, it, expect } from 'vitest';
import {
  WORKBUDDY_TOP20_MIGRATION_MAP,
  isWorkBuddyMigrationSkill,
  getWorkBuddyMigrationInfo,
} from '../skillsMigrationMap';

describe('skillsMigrationMap', () => {
  it('should have exactly 20 essential migration skills', () => {
    expect(WORKBUDDY_TOP20_MIGRATION_MAP.length).toBe(20);
  });

  it('should ensure all items have valid non-empty fields', () => {
    const ids = new Set<string>();
    for (const item of WORKBUDDY_TOP20_MIGRATION_MAP) {
      expect(item.wbSkillName).toBeTruthy();
      expect(item.myrmSkillId).toBeTruthy();
      expect(item.summaryZh).toBeTruthy();
      expect(item.summaryEn).toBeTruthy();
      expect(item.enhancementsZh.length).toBeGreaterThan(0);
      expect(item.enhancementsEn.length).toBeGreaterThan(0);
      expect(item.recommendedPrompt).toBeTruthy();

      // Ensure no duplicate skill IDs in the top 20 list
      expect(ids.has(item.myrmSkillId)).toBe(false);
      ids.add(item.myrmSkillId);
    }
  });

  it('should correctly identify migration skills and return details', () => {
    expect(isWorkBuddyMigrationSkill('office-document')).toBe(true);
    expect(isWorkBuddyMigrationSkill('host-server-ops')).toBe(true);
    expect(isWorkBuddyMigrationSkill('non-existent-skill-xyz')).toBe(false);

    const info = getWorkBuddyMigrationInfo('office-document');
    expect(info).toBeDefined();
    expect(info?.myrmSkillId).toBe('office-document');
    expect(info?.wbSkillName).toContain('Office Document');
  });
});
