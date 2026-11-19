/**
 * What the thinking-intensity control remembers for each model: a saved level or custom value comes back on mount
 * and on model switches, and a browser which refuses storage does not break it.
 */
import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useProviderStore from '@/store/useProviderStore';
import { getThinkingEffort, setGlobalIntensity } from '../ThinkingIntensityButton';
import {
  REASONING_MODEL,
  blockStorage,
  configureModel,
  openCustomField,
  openPopover,
  renderButton,
  resetThinkingIntensityKit,
} from './thinkingIntensityKit';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

describe('ThinkingIntensityButton', () => {
  beforeEach(resetThinkingIntensityKit);

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('per-model memory', () => {
    it('restores the level saved for the model on mount', () => {
      localStorage.setItem(`thinkingIntensity_${REASONING_MODEL}`, 'xhigh');
      renderButton();

      expect(getThinkingEffort()).toBe('xhigh');
      expect(screen.getByRole('button', { name: 'Thinking Intensity: X-High' })).toBeInTheDocument();
    });

    it('restores a saved custom value, which wins over a saved level', () => {
      localStorage.setItem(`thinkingIntensity_${REASONING_MODEL}`, 'low');
      localStorage.setItem(`thinkingIntensityCustom_${REASONING_MODEL}`, '24k');
      renderButton();

      expect(getThinkingEffort()).toBe('24k');
    });

    it('ignores a saved level it does not know', () => {
      localStorage.setItem(`thinkingIntensity_${REASONING_MODEL}`, 'turbo');
      renderButton();

      expect(getThinkingEffort()).toBeUndefined();
    });

    it('restores a saved off, which differs from having chosen nothing', () => {
      localStorage.setItem(`thinkingIntensity_${REASONING_MODEL}`, 'off');
      renderButton();

      expect(getThinkingEffort()).toBe('off');
    });

    it('swaps in the saved choice of each model, and goes back to auto for a model with none', () => {
      localStorage.setItem('thinkingIntensity_o3-mini', 'high');
      localStorage.setItem('thinkingIntensity_o4-mini', 'low');
      renderButton();
      expect(getThinkingEffort()).toBe('high');

      act(() => configureModel('o4-mini'));
      expect(getThinkingEffort()).toBe('low');

      act(() => configureModel('claude-sonnet-4'));
      expect(getThinkingEffort()).toBeUndefined();

      act(() => configureModel('o3-mini'));
      expect(getThinkingEffort()).toBe('high');
    });

    it('keeps the current choice when the model list refreshes without changing the model', () => {
      renderButton();
      act(() => setGlobalIntensity('medium'));

      act(() => useProviderStore.setState({ providers: [] }));

      expect(getThinkingEffort()).toBe('medium');
    });
  });

  // A refused write is kept by the page, so each of these uses a model name no other test touches.
  describe('when the browser refuses storage access', () => {
    it('mounts and applies a level', async () => {
      blockStorage();
      configureModel('blocked-level-model', true);
      const user = userEvent.setup();
      renderButton();
      const dialog = await openPopover(user);

      await user.click(within(dialog).getByRole('button', { name: 'High' }));

      expect(getThinkingEffort()).toBe('high');
      expect(screen.getByRole('button', { name: 'Thinking Intensity: High' })).toBeInTheDocument();
    });

    it('applies a custom value', async () => {
      blockStorage();
      configureModel('blocked-custom-model', true);
      const user = userEvent.setup();
      renderButton();
      const field = await openCustomField(user);

      await user.type(field, '16k{Enter}');

      expect(getThinkingEffort()).toBe('16k');
    });

    it('still remembers the choice made for each model for the rest of the page', async () => {
      blockStorage();
      configureModel('blocked-first-model', true);
      const user = userEvent.setup();
      renderButton();
      const dialog = await openPopover(user);
      await user.click(within(dialog).getByRole('button', { name: 'Max' }));

      act(() => configureModel('blocked-second-model', true));
      expect(getThinkingEffort()).toBeUndefined();

      act(() => configureModel('blocked-first-model', true));
      expect(getThinkingEffort()).toBe('max');
    });
  });
});
