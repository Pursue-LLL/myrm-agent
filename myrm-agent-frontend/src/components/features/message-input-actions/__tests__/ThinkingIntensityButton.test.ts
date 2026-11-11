import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  INTENSITY_OPTIONS,
  getThinkingEffort,
  setGlobalCustomValue,
  setGlobalIntensity,
  useGlobalIntensity,
} from '../ThinkingIntensityButton';

// The saved-choice keys are what users' browsers already hold, so they are part of the contract.
const LEVEL_KEY = 'thinkingIntensity_test-model';
const CUSTOM_KEY = 'thinkingIntensityCustom_test-model';

describe('thinking intensity choice', () => {
  beforeEach(() => {
    localStorage.clear();
    setGlobalIntensity('off');
  });

  it('offers off, low, medium, high, xhigh and max, in that order', () => {
    expect(INTENSITY_OPTIONS.map((option) => option.value)).toEqual(['off', 'low', 'medium', 'high', 'xhigh', 'max']);
  });

  describe('getThinkingEffort', () => {
    it('is undefined while the intensity is off', () => {
      expect(getThinkingEffort()).toBeUndefined();
    });

    it.each(['low', 'medium', 'high', 'xhigh', 'max'] as const)('is "%s" once that level is chosen', (level) => {
      setGlobalIntensity(level);

      expect(getThinkingEffort()).toBe(level);
    });

    it('follows each change, back to undefined on off', () => {
      for (const { value } of INTENSITY_OPTIONS) {
        setGlobalIntensity(value);

        expect(getThinkingEffort()).toBe(value === 'off' ? undefined : value);
      }
    });
  });

  describe('setGlobalIntensity', () => {
    it('saves the level for the model', () => {
      setGlobalIntensity('xhigh', 'test-model');

      expect(localStorage.getItem(LEVEL_KEY)).toBe('xhigh');
    });

    it('forgets the saved level on off', () => {
      setGlobalIntensity('high', 'test-model');

      setGlobalIntensity('off', 'test-model');

      expect(localStorage.getItem(LEVEL_KEY)).toBeNull();
    });

    it('replaces a saved custom value', () => {
      localStorage.setItem(CUSTOM_KEY, 'custom-val');

      setGlobalIntensity('xhigh', 'test-model');

      expect(localStorage.getItem(CUSTOM_KEY)).toBeNull();
      expect(localStorage.getItem(LEVEL_KEY)).toBe('xhigh');
    });

    it('saves nothing without a model, and still applies', () => {
      setGlobalIntensity('max');

      expect(localStorage.length).toBe(0);
      expect(getThinkingEffort()).toBe('max');
    });
  });

  describe('setGlobalCustomValue', () => {
    it('applies the value as the effort', () => {
      setGlobalCustomValue('160k');

      expect(getThinkingEffort()).toBe('160k');
    });

    it('saves the value for the model and drops the saved level', () => {
      setGlobalIntensity('high', 'test-model');

      setGlobalCustomValue('999', 'test-model');

      expect(localStorage.getItem(LEVEL_KEY)).toBeNull();
      expect(localStorage.getItem(CUSTOM_KEY)).toBe('999');
    });

    it('forgets the saved value when cleared', () => {
      setGlobalCustomValue('999', 'test-model');

      setGlobalCustomValue('', 'test-model');

      expect(localStorage.getItem(CUSTOM_KEY)).toBeNull();
      expect(getThinkingEffort()).toBeUndefined();
    });

    it('saves nothing without a model, and still applies', () => {
      setGlobalCustomValue('override');

      expect(localStorage.length).toBe(0);
      expect(getThinkingEffort()).toBe('override');
    });

    it('wins over a level chosen earlier', () => {
      setGlobalIntensity('max');

      setGlobalCustomValue('override-value');

      expect(getThinkingEffort()).toBe('override-value');
    });

    it('is replaced when a level is chosen again', () => {
      setGlobalCustomValue('my-custom', 'test-model');

      setGlobalIntensity('xhigh', 'test-model');

      expect(getThinkingEffort()).toBe('xhigh');
      expect(localStorage.getItem(CUSTOM_KEY)).toBeNull();
    });
  });

  describe('useGlobalIntensity', () => {
    it('re-renders its readers when the choice changes, and only then', () => {
      let renders = 0;
      const { result } = renderHook(() => {
        renders += 1;
        return useGlobalIntensity();
      });
      expect(result.current).toEqual({ intensity: 'off', customValue: '' });
      const initialRenders = renders;

      act(() => setGlobalIntensity('off'));
      expect(renders).toBe(initialRenders);

      act(() => setGlobalIntensity('high'));
      expect(result.current).toEqual({ intensity: 'high', customValue: '' });

      act(() => setGlobalCustomValue('32k'));
      expect(result.current).toEqual({ intensity: 'off', customValue: '32k' });

      act(() => setGlobalCustomValue('32k'));
      expect(renders).toBe(initialRenders + 2);
    });
  });
});
