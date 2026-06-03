import { describe, expect, it, beforeEach } from 'vitest';

import {
  generateCompanion,
  evolveStats,
  getTitle,
  getRarityAbilities,
  getObserverLimits,
  getEnhancedPersonality,
  checkEvolution,
  computeMood,
  SPECIES,
  RARITIES,
  HATS,
  STAT_NAMES,
  MOODS,
  EVOLUTION_REQUIREMENTS,
  type CompanionBones,
  type MoodInput,
  type CompanionStats,
} from '../companionGenerator';

describe('companionGenerator', () => {
  describe('generateCompanion', () => {
    it('returns deterministic result for same userId', () => {
      const a = generateCompanion('test-user-1');
      const b = generateCompanion('test-user-1');
      expect(a).toEqual(b);
    });

    it('returns different results for different userIds', () => {
      const a = generateCompanion('user-alpha');
      const b = generateCompanion('user-beta');
      expect(a.species === b.species && a.rarity === b.rarity && a.defaultName === b.defaultName).toBe(false);
    });

    it('produces valid species from SPECIES list', () => {
      for (let i = 0; i < 20; i++) {
        const bones = generateCompanion(`gen-species-${i}`);
        expect(SPECIES).toContain(bones.species);
      }
    });

    it('produces valid rarity from RARITIES list', () => {
      for (let i = 0; i < 20; i++) {
        const bones = generateCompanion(`gen-rarity-${i}`);
        expect(RARITIES).toContain(bones.rarity);
      }
    });

    it('has correct stars matching rarity index + 1', () => {
      for (let i = 0; i < 20; i++) {
        const bones = generateCompanion(`gen-stars-${i}`);
        expect(bones.stars).toBe(RARITIES.indexOf(bones.rarity) + 1);
      }
    });

    it('has all stat values in [1, 100]', () => {
      for (let i = 0; i < 30; i++) {
        const bones = generateCompanion(`gen-stats-${i}`);
        for (const stat of STAT_NAMES) {
          expect(bones.stats[stat]).toBeGreaterThanOrEqual(1);
          expect(bones.stats[stat]).toBeLessThanOrEqual(100);
        }
      }
    });

    it('peakStat has the floor+50 boost applied', () => {
      for (let i = 0; i < 20; i++) {
        const bones = generateCompanion(`gen-peak-${i}`);
        const peakValue = bones.stats[bones.peakStat];
        expect(peakValue).toBeGreaterThanOrEqual(55);
      }
    });

    it('hat is null for Common rarity', () => {
      const commonBones: CompanionBones[] = [];
      for (let i = 0; i < 200; i++) {
        const bones = generateCompanion(`gen-hat-common-${i}`);
        if (bones.rarity === 'Common') commonBones.push(bones);
      }
      expect(commonBones.length).toBeGreaterThan(0);
      for (const bones of commonBones) {
        expect(bones.hat).toBeNull();
      }
    });

    it('hat is from HATS list when non-null', () => {
      for (let i = 0; i < 100; i++) {
        const bones = generateCompanion(`gen-hat-${i}`);
        if (bones.hat !== null) {
          expect(HATS).toContain(bones.hat);
        }
      }
    });

    it('personality includes peak and dump traits', () => {
      const bones = generateCompanion('gen-personality');
      expect(bones.personality).toContain(' but ');
    });

    it('defaultName is a non-empty string', () => {
      const bones = generateCompanion('gen-name');
      expect(bones.defaultName.length).toBeGreaterThan(0);
    });

    it('shiny is a boolean', () => {
      const bones = generateCompanion('gen-shiny');
      expect(typeof bones.shiny).toBe('boolean');
    });
  });

  describe('evolveStats', () => {
    let baseBones: CompanionBones;

    beforeEach(() => {
      baseBones = generateCompanion('evolve-test-user');
    });

    it('returns base stats unchanged when target is Common', () => {
      const result = evolveStats(baseBones.stats, baseBones.peakStat, 'evolve-test-user', 'Common');
      expect(result).toEqual(baseBones.stats);
    });

    it('boosts stats for higher rarities', () => {
      const base = evolveStats(baseBones.stats, baseBones.peakStat, 'evolve-test-user', 'Common');
      const evolved = evolveStats(baseBones.stats, baseBones.peakStat, 'evolve-test-user', 'Rare');
      const baseTotal = STAT_NAMES.reduce((sum, s) => sum + base[s], 0);
      const evolvedTotal = STAT_NAMES.reduce((sum, s) => sum + evolved[s], 0);
      expect(evolvedTotal).toBeGreaterThan(baseTotal);
    });

    it('caps stats at 100', () => {
      const maxStats: CompanionStats = { debugging: 95, patience: 95, chaos: 95, wisdom: 95, snark: 95 };
      const result = evolveStats(maxStats, 'debugging', 'cap-test', 'Legendary');
      for (const stat of STAT_NAMES) {
        expect(result[stat]).toBeLessThanOrEqual(100);
      }
    });

    it('is deterministic for same inputs', () => {
      const a = evolveStats(baseBones.stats, baseBones.peakStat, 'evolve-test-user', 'Epic');
      const b = evolveStats(baseBones.stats, baseBones.peakStat, 'evolve-test-user', 'Epic');
      expect(a).toEqual(b);
    });
  });

  describe('getTitle', () => {
    it('returns null for Common rarity', () => {
      expect(getTitle('debugging', 'Common')).toBeNull();
    });

    it('returns English title for Uncommon+', () => {
      const title = getTitle('debugging', 'Uncommon', 'en');
      expect(title).toBe('The Analytical');
    });

    it('returns Chinese title when locale is zh', () => {
      const title = getTitle('wisdom', 'Rare', 'zh');
      expect(title).toBe('智慧贤者');
    });

    it('returns a title for every stat name with non-Common rarity', () => {
      for (const stat of STAT_NAMES) {
        const title = getTitle(stat, 'Epic');
        expect(title).not.toBeNull();
        expect(typeof title).toBe('string');
      }
    });
  });

  describe('getRarityAbilities', () => {
    it('Common has no abilities unlocked', () => {
      const abilities = getRarityAbilities('Common');
      expect(abilities.title).toBe(false);
      expect(abilities.enhancedPersonality).toBe(false);
      expect(abilities.observerBoost).toBe(false);
      expect(abilities.legendaryFlair).toBe(false);
    });

    it('Uncommon unlocks title only', () => {
      const abilities = getRarityAbilities('Uncommon');
      expect(abilities.title).toBe(true);
      expect(abilities.enhancedPersonality).toBe(false);
    });

    it('Rare unlocks title + enhancedPersonality', () => {
      const abilities = getRarityAbilities('Rare');
      expect(abilities.title).toBe(true);
      expect(abilities.enhancedPersonality).toBe(true);
      expect(abilities.observerBoost).toBe(false);
    });

    it('Epic unlocks up to observerBoost', () => {
      const abilities = getRarityAbilities('Epic');
      expect(abilities.observerBoost).toBe(true);
      expect(abilities.legendaryFlair).toBe(false);
    });

    it('Legendary unlocks everything', () => {
      const abilities = getRarityAbilities('Legendary');
      expect(abilities.title).toBe(true);
      expect(abilities.enhancedPersonality).toBe(true);
      expect(abilities.observerBoost).toBe(true);
      expect(abilities.legendaryFlair).toBe(true);
    });
  });

  describe('getObserverLimits', () => {
    it('returns valid limits for every rarity', () => {
      for (const rarity of RARITIES) {
        const limits = getObserverLimits(rarity);
        expect(limits.maxPerSession).toBeGreaterThan(0);
        expect(limits.displayDurationMs).toBeGreaterThan(0);
      }
    });

    it('higher rarities have higher maxPerSession', () => {
      const common = getObserverLimits('Common');
      const legendary = getObserverLimits('Legendary');
      expect(legendary.maxPerSession).toBeGreaterThan(common.maxPerSession);
    });
  });

  describe('getEnhancedPersonality', () => {
    it('returns base trait for Common', () => {
      const bones = generateCompanion('personality-common');
      const result = getEnhancedPersonality(bones, 'Common');
      expect(result.length).toBeGreaterThan(0);
      expect(result).not.toContain(' and ');
    });

    it('returns dual traits for Rare', () => {
      const bones = generateCompanion('personality-rare');
      const result = getEnhancedPersonality(bones, 'Rare');
      expect(result).toContain(' and ');
    });

    it('returns intensified description for Epic', () => {
      const bones = generateCompanion('personality-epic');
      const result = getEnhancedPersonality(bones, 'Epic');
      expect(result).toContain('deeply');
      expect(result).toContain('remarkably');
    });

    it('returns legendary description with insights marker', () => {
      const bones = generateCompanion('personality-legendary');
      const result = getEnhancedPersonality(bones, 'Legendary');
      expect(result).toContain('profound insights');
    });
  });

  describe('checkEvolution', () => {
    it('Legendary cannot evolve further', () => {
      const result = checkEvolution('Legendary', 999, Date.now() - 365 * 86400000, 999);
      expect(result.canEvolve).toBe(false);
      expect(result.nextRarity).toBeNull();
    });

    it('Common can evolve when requirements met', () => {
      const req = EVOLUTION_REQUIREMENTS['Common']!;
      const hatchedAt = Date.now() - (req.daysActive + 1) * 86400000;
      const result = checkEvolution('Common', req.petCount, hatchedAt, req.conversationCount);
      expect(result.canEvolve).toBe(true);
      expect(result.nextRarity).toBe('Uncommon');
    });

    it('Common cannot evolve when requirements not met', () => {
      const result = checkEvolution('Common', 0, Date.now(), 0);
      expect(result.canEvolve).toBe(false);
      expect(result.nextRarity).toBe('Uncommon');
    });

    it('returns progress info for non-Legendary', () => {
      const result = checkEvolution('Rare', 50, Date.now() - 10 * 86400000, 20);
      expect(result.progress).not.toBeNull();
      expect(result.progress!.petCount.required).toBeGreaterThan(0);
    });

    it('handles null hatchedAt gracefully', () => {
      const result = checkEvolution('Common', 100, null, 100);
      expect(result.progress!.daysActive.current).toBe(0);
    });
  });

  describe('computeMood', () => {
    const baseMoodInput: MoodInput = {
      petCount: 0,
      lastPetAt: null,
      conversationCount: 0,
      lastInteractionAt: Date.now(),
      isGoalComplete: false,
      isEvolutionRecent: false,
    };

    it('exports MOODS constant with 5 values', () => {
      expect(MOODS).toHaveLength(5);
      expect(MOODS).toContain('neutral');
      expect(MOODS).toContain('happy');
      expect(MOODS).toContain('curious');
      expect(MOODS).toContain('excited');
      expect(MOODS).toContain('sleepy');
    });

    it('returns neutral for fresh user', () => {
      expect(computeMood(baseMoodInput)).toBe('neutral');
    });

    it('returns excited when goal is complete', () => {
      expect(computeMood({ ...baseMoodInput, isGoalComplete: true })).toBe('excited');
    });

    it('returns excited when evolution is recent', () => {
      expect(computeMood({ ...baseMoodInput, isEvolutionRecent: true })).toBe('excited');
    });

    it('excited takes priority over happy', () => {
      expect(
        computeMood({
          ...baseMoodInput,
          isGoalComplete: true,
          petCount: 10,
          lastPetAt: Date.now(),
        }),
      ).toBe('excited');
    });

    it('returns happy when pet count >= 3 and recent pet', () => {
      expect(
        computeMood({
          ...baseMoodInput,
          petCount: 3,
          lastPetAt: Date.now(),
        }),
      ).toBe('happy');
    });

    it('does not return happy if pet was long ago', () => {
      expect(
        computeMood({
          ...baseMoodInput,
          petCount: 10,
          lastPetAt: Date.now() - 10 * 60 * 1000,
        }),
      ).not.toBe('happy');
    });

    it('returns curious when conversation count >= 5', () => {
      expect(
        computeMood({
          ...baseMoodInput,
          conversationCount: 5,
        }),
      ).toBe('curious');
    });

    it('returns sleepy when idle for > 30 minutes', () => {
      expect(
        computeMood({
          ...baseMoodInput,
          lastInteractionAt: Date.now() - 31 * 60 * 1000,
        }),
      ).toBe('sleepy');
    });

    it('returns sleepy when lastInteractionAt is null', () => {
      expect(
        computeMood({
          ...baseMoodInput,
          lastInteractionAt: null,
        }),
      ).toBe('sleepy');
    });
  });
});
