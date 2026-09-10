import { describe, it, expect } from 'vitest';
import {
  WB_TOP20_SKILL_MIGRATION_MAP,
  findMigratedSkill,
} from '../skillMigrationMap';

describe('WB_TOP20_SKILL_MIGRATION_MAP', () => {
  it('should contain exactly 20 essential skills', () => {
    expect(WB_TOP20_SKILL_MIGRATION_MAP).toHaveLength(20);
  });

  it('every entry should have required non-empty fields', () => {
    WB_TOP20_SKILL_MIGRATION_MAP.forEach((item) => {
      expect(item.wbSkillId).toBeTruthy();
      expect(item.wbNameZh).toBeTruthy();
      expect(item.wbNameEn).toBeTruthy();
      expect(item.myrmSkillId).toBeTruthy();
      expect(['exact', 'superset', 'composite']).toContain(item.matchQuality);
      expect(item.enhancementsZh).toBeTruthy();
      expect(item.enhancementsEn).toBeTruthy();
    });
  });

  it('should have unique wbSkillId and myrmSkillId per item', () => {
    const wbIds = WB_TOP20_SKILL_MIGRATION_MAP.map((i) => i.wbSkillId);
    const uniqueWbIds = new Set(wbIds);
    expect(uniqueWbIds.size).toBe(wbIds.length);
  });

  it('findMigratedSkill should match by exact wbSkillId or myrmSkillId', () => {
    const meeting = findMigratedSkill('wb-meeting-minutes');
    expect(meeting).toBeDefined();
    expect(meeting?.myrmSkillId).toBe('voice-memo-synthesizer');

    const office = findMigratedSkill('office-document');
    expect(office).toBeDefined();
    expect(office?.wbSkillId).toBe('wb-office-doc-helper');
  });

  it('findMigratedSkill should match by keyword or scenario', () => {
    const research = findMigratedSkill('深度联网');
    expect(research).toBeDefined();
    expect(research?.myrmSkillId).toBe('deep-research');

    const board = findMigratedSkill('番茄钟');
    expect(board).toBeDefined();
    expect(board?.myrmSkillId).toBe('personal-life-workbench');
  });

  it('findMigratedSkill should return undefined for unmatched queries', () => {
    expect(findMigratedSkill('')).toBeUndefined();
    expect(findMigratedSkill('   ')).toBeUndefined();
    expect(findMigratedSkill('non-existent-xyz-random-123')).toBeUndefined();
  });
});
