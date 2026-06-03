import { describe, it, expect, beforeEach } from 'vitest';

import {
  setGlobalIntensity,
  setGlobalCustomValue,
  getThinkingEffort,
  type IntensityLevel,
} from '../ThinkingIntensityButton';

const STORAGE_PREFIX = 'thinkingIntensity_';
const CUSTOM_STORAGE_PREFIX = 'thinkingIntensityCustom_';

const ALL_LEVELS: IntensityLevel[] = ['off', 'low', 'medium', 'high', 'xhigh', 'max'];

function resetGlobalState() {
  setGlobalIntensity('off');
}

describe('ThinkingIntensityButton - core logic', () => {
  beforeEach(() => {
    localStorage.clear();
    resetGlobalState();
  });

  describe('IntensityLevel type completeness', () => {
    it('includes all 6 levels including xhigh', () => {
      expect(ALL_LEVELS).toHaveLength(6);
      expect(ALL_LEVELS).toContain('xhigh');
      expect(ALL_LEVELS.indexOf('xhigh')).toBe(4);
    });
  });

  describe('getThinkingEffort', () => {
    it('returns undefined when intensity is off', () => {
      setGlobalIntensity('off');
      expect(getThinkingEffort()).toBeUndefined();
    });

    it.each(['low', 'medium', 'high', 'xhigh', 'max'] as const)('returns "%s" when intensity is %s', (level) => {
      setGlobalIntensity(level);
      expect(getThinkingEffort()).toBe(level);
    });
  });

  describe('setGlobalIntensity with localStorage', () => {
    it('persists preset to localStorage when modelName provided', () => {
      setGlobalIntensity('xhigh', 'claude-sonnet-4-20250514');
      expect(localStorage.getItem(`${STORAGE_PREFIX}claude-sonnet-4-20250514`)).toBe('xhigh');
    });

    it('removes localStorage key when switching to off', () => {
      setGlobalIntensity('high', 'test-model');
      expect(localStorage.getItem(`${STORAGE_PREFIX}test-model`)).toBe('high');
      setGlobalIntensity('off', 'test-model');
      expect(localStorage.getItem(`${STORAGE_PREFIX}test-model`)).toBeNull();
    });

    it('clears custom storage when switching to a preset', () => {
      localStorage.setItem(`${CUSTOM_STORAGE_PREFIX}test-model`, 'custom-val');
      setGlobalIntensity('xhigh', 'test-model');
      expect(localStorage.getItem(`${CUSTOM_STORAGE_PREFIX}test-model`)).toBeNull();
      expect(localStorage.getItem(`${STORAGE_PREFIX}test-model`)).toBe('xhigh');
    });

    it('does not persist when modelName is not provided', () => {
      setGlobalIntensity('max');
      expect(localStorage.getItem(`${STORAGE_PREFIX}`)).toBeNull();
      expect(getThinkingEffort()).toBe('max');
    });
  });

  describe('global state reactivity', () => {
    it('updates getThinkingEffort after setGlobalIntensity', () => {
      expect(getThinkingEffort()).toBeUndefined();
      setGlobalIntensity('xhigh');
      expect(getThinkingEffort()).toBe('xhigh');
      setGlobalIntensity('low');
      expect(getThinkingEffort()).toBe('low');
      setGlobalIntensity('off');
      expect(getThinkingEffort()).toBeUndefined();
    });

    it('transitions through all levels correctly', () => {
      for (const level of ALL_LEVELS) {
        setGlobalIntensity(level);
        const expected = level === 'off' ? undefined : level;
        expect(getThinkingEffort()).toBe(expected);
      }
    });
  });

  describe('setGlobalCustomValue', () => {
    it('sets custom value and returns it via getThinkingEffort', () => {
      setGlobalCustomValue('160k');
      expect(getThinkingEffort()).toBe('160k');
    });

    it('persists custom value to localStorage when modelName provided', () => {
      setGlobalCustomValue('my-custom', 'test-model');
      expect(localStorage.getItem(`${CUSTOM_STORAGE_PREFIX}test-model`)).toBe('my-custom');
      expect(localStorage.getItem(`${STORAGE_PREFIX}test-model`)).toBeNull();
    });

    it('clears preset storage when setting custom value', () => {
      setGlobalIntensity('high', 'test-model');
      expect(localStorage.getItem(`${STORAGE_PREFIX}test-model`)).toBe('high');

      setGlobalCustomValue('999', 'test-model');
      expect(localStorage.getItem(`${STORAGE_PREFIX}test-model`)).toBeNull();
      expect(localStorage.getItem(`${CUSTOM_STORAGE_PREFIX}test-model`)).toBe('999');
    });

    it('custom value takes priority over preset in getThinkingEffort', () => {
      setGlobalIntensity('max');
      expect(getThinkingEffort()).toBe('max');

      setGlobalCustomValue('override-value');
      expect(getThinkingEffort()).toBe('override-value');
    });

    it('switching back to preset clears custom value', () => {
      setGlobalCustomValue('my-custom', 'test-model');
      expect(getThinkingEffort()).toBe('my-custom');

      setGlobalIntensity('xhigh', 'test-model');
      expect(getThinkingEffort()).toBe('xhigh');
      expect(localStorage.getItem(`${CUSTOM_STORAGE_PREFIX}test-model`)).toBeNull();
    });
  });

  describe('xhigh-specific behavior', () => {
    it('xhigh is stored and retrieved correctly via localStorage roundtrip', () => {
      setGlobalIntensity('xhigh', 'my-model');
      expect(localStorage.getItem(`${STORAGE_PREFIX}my-model`)).toBe('xhigh');

      resetGlobalState();
      expect(getThinkingEffort()).toBeUndefined();

      const stored = localStorage.getItem(`${STORAGE_PREFIX}my-model`);
      expect(stored).toBe('xhigh');
    });

    it('xhigh is positioned between high and max', () => {
      const highIdx = ALL_LEVELS.indexOf('high');
      const xhighIdx = ALL_LEVELS.indexOf('xhigh');
      const maxIdx = ALL_LEVELS.indexOf('max');
      expect(xhighIdx).toBe(highIdx + 1);
      expect(xhighIdx).toBe(maxIdx - 1);
    });
  });
});
