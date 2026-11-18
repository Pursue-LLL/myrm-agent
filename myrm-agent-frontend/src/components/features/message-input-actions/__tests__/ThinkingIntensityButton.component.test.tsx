/**
 * The thinking-intensity control as a user meets it: when it shows up, what the trigger says, and how a level or a
 * custom value is chosen and saved for the model. Restoring those choices later is in
 * ThinkingIntensityButton.memory.test.tsx.
 */
import { act, fireEvent, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getThinkingEffort, setGlobalIntensity } from '../ThinkingIntensityButton';
import {
  PLAIN_MODEL,
  REASONING_MODEL,
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

  describe('when it shows up', () => {
    it('renders nothing without a configured model', () => {
      configureModel(null);
      const { container } = renderButton();

      expect(container).toBeEmptyDOMElement();
    });

    it('renders nothing for a model that cannot reason', () => {
      configureModel(PLAIN_MODEL);
      const { container } = renderButton();

      expect(container).toBeEmptyDOMElement();
    });

    it('shows for a model whose reported capability says it can reason, whatever its name', () => {
      configureModel(PLAIN_MODEL, true);
      renderButton();

      expect(screen.getByRole('button', { name: 'Thinking Intensity' })).toBeInTheDocument();
    });

    it('hides for a reasoning-named model whose reported capability says it cannot', () => {
      configureModel(REASONING_MODEL, false);
      const { container } = renderButton();

      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('trigger', () => {
    it('is named after the control while the intensity is auto, with no level text', () => {
      renderButton();

      const trigger = screen.getByRole('button', { name: 'Thinking Intensity' });
      expect(trigger).toHaveTextContent('');
    });

    it('says so when thinking is asked to be off', () => {
      localStorage.setItem(`thinkingIntensity_${REASONING_MODEL}`, 'off');
      renderButton();

      expect(screen.getByRole('button', { name: 'Thinking Intensity: Off' })).toHaveTextContent('Off');
    });

    it('carries the active level in its text and name', () => {
      localStorage.setItem(`thinkingIntensity_${REASONING_MODEL}`, 'high');
      renderButton();

      expect(screen.getByRole('button', { name: 'Thinking Intensity: High' })).toHaveTextContent('High');
    });

    it('shows a custom value in place of a level', () => {
      localStorage.setItem(`thinkingIntensityCustom_${REASONING_MODEL}`, '160k');
      renderButton();

      expect(screen.getByRole('button', { name: 'Thinking Intensity: 160k' })).toHaveTextContent('160k');
    });

    it('follows changes made elsewhere', () => {
      renderButton();

      act(() => setGlobalIntensity('low'));

      expect(screen.getByRole('button', { name: 'Thinking Intensity: Low' })).toBeInTheDocument();
    });
  });

  describe('choosing a level', () => {
    it('lists every level and the custom entry, with only the current one pressed', async () => {
      localStorage.setItem(`thinkingIntensity_${REASONING_MODEL}`, 'xhigh');
      renderButton();

      const dialog = await openPopover(userEvent.setup());

      expect(within(dialog).getAllByRole('button')).toHaveLength(8);
      const pressed = within(dialog).getAllByRole('button', { pressed: true });
      expect(pressed).toHaveLength(1);
      expect(pressed[0]).toHaveTextContent('X-High');
    });

    it('applies the level, saves it for the model and closes', async () => {
      const user = userEvent.setup();
      renderButton();
      const dialog = await openPopover(user);

      await user.click(within(dialog).getByRole('button', { name: 'High' }));

      expect(getThinkingEffort()).toBe('high');
      expect(localStorage.getItem(`thinkingIntensity_${REASONING_MODEL}`)).toBe('high');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Thinking Intensity: High' })).toBeInTheDocument();
    });

    it('marks auto as the default and starts on it', async () => {
      renderButton();

      const dialog = await openPopover(userEvent.setup());

      const auto = within(dialog).getByRole('button', { name: /^Auto/ });
      expect(auto).toHaveAttribute('aria-pressed', 'true');
      expect(auto).toHaveTextContent('Default');
      expect(getThinkingEffort()).toBeUndefined();
    });

    it('forgets the saved level when switching back to auto', async () => {
      localStorage.setItem(`thinkingIntensity_${REASONING_MODEL}`, 'high');
      const user = userEvent.setup();
      renderButton();
      const dialog = await openPopover(user);

      await user.click(within(dialog).getByRole('button', { name: /^Auto/ }));

      expect(getThinkingEffort()).toBeUndefined();
      expect(localStorage.getItem(`thinkingIntensity_${REASONING_MODEL}`)).toBeNull();
    });

    it('asks for no thinking on off, which is a choice of its own that is saved for the model', async () => {
      const user = userEvent.setup();
      renderButton();
      const dialog = await openPopover(user);

      await user.click(within(dialog).getByRole('button', { name: 'Off' }));

      expect(getThinkingEffort()).toBe('off');
      expect(localStorage.getItem(`thinkingIntensity_${REASONING_MODEL}`)).toBe('off');
      expect(screen.getByRole('button', { name: 'Thinking Intensity: Off' })).toBeInTheDocument();
    });

    it('replaces a saved custom value when a level is chosen', async () => {
      localStorage.setItem(`thinkingIntensityCustom_${REASONING_MODEL}`, '24k');
      const user = userEvent.setup();
      renderButton();
      const dialog = await openPopover(user);

      await user.click(within(dialog).getByRole('button', { name: 'Max' }));

      expect(getThinkingEffort()).toBe('max');
      expect(localStorage.getItem(`thinkingIntensityCustom_${REASONING_MODEL}`)).toBeNull();
      expect(localStorage.getItem(`thinkingIntensity_${REASONING_MODEL}`)).toBe('max');
    });
  });

  describe('custom value', () => {
    it('keeps apply disabled until something other than blanks is typed, and focuses the field', async () => {
      const user = userEvent.setup();
      renderButton();
      const field = await openCustomField(user);
      const apply = screen.getByRole('button', { name: 'OK' });

      expect(field).toHaveFocus();
      expect(apply).toBeDisabled();

      await user.type(field, '   ');
      expect(apply).toBeDisabled();

      await user.type(field, '16k');
      expect(apply).toBeEnabled();
    });

    it('applies the trimmed value on Enter, saves it for the model and closes', async () => {
      const user = userEvent.setup();
      renderButton();
      const field = await openCustomField(user);

      await user.type(field, '  16k {Enter}');

      expect(getThinkingEffort()).toBe('16k');
      expect(localStorage.getItem(`thinkingIntensityCustom_${REASONING_MODEL}`)).toBe('16k');
      expect(localStorage.getItem(`thinkingIntensity_${REASONING_MODEL}`)).toBeNull();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Thinking Intensity: 16k' })).toBeInTheDocument();
    });

    it('applies through the apply button', async () => {
      const user = userEvent.setup();
      renderButton();
      const field = await openCustomField(user);

      await user.type(field, '8192');
      await user.click(screen.getByRole('button', { name: 'OK' }));

      expect(getThinkingEffort()).toBe('8192');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('ignores Enter while an input method is composing', async () => {
      const user = userEvent.setup();
      renderButton();
      const field = await openCustomField(user);
      await user.type(field, '16k');

      fireEvent.keyDown(field, { key: 'Enter', isComposing: true });

      expect(getThinkingEffort()).toBeUndefined();
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('ignores Enter on a blank value', async () => {
      const user = userEvent.setup();
      renderButton();
      const field = await openCustomField(user);

      await user.type(field, '   {Enter}');

      expect(getThinkingEffort()).toBeUndefined();
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('leaves the intensity alone and shows the entry again on the next open after Escape', async () => {
      const user = userEvent.setup();
      renderButton();
      const field = await openCustomField(user);
      await user.type(field, '16k');

      await user.keyboard('{Escape}');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      const dialog = await openPopover(user);

      expect(getThinkingEffort()).toBeUndefined();
      expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument();
      expect(within(dialog).getByRole('button', { name: 'Custom' })).toBeInTheDocument();
    });

    it('shows the current custom value in place of "Custom" and prefills the field with it', async () => {
      localStorage.setItem(`thinkingIntensityCustom_${REASONING_MODEL}`, '8k');
      const user = userEvent.setup();
      renderButton();

      const dialog = await openPopover(user);
      expect(within(dialog).getByRole('button', { name: '8k', pressed: true })).toBeInTheDocument();
      expect(within(dialog).queryByRole('button', { name: 'Custom' })).not.toBeInTheDocument();

      await user.click(within(dialog).getByRole('button', { name: '8k' }));
      expect(screen.getByRole('textbox', { name: 'Custom' })).toHaveValue('8k');
    });
  });
});
