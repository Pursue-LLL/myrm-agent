/**
 * The thinking-intensity control as a user meets it: when it shows up, what the trigger says, how a level or a
 * custom value is chosen and saved per model, and that a browser which refuses storage does not break it.
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getInitialDefaultModelConfig, type CustomModelInfo } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';
import ThinkingIntensityButton, {
  getThinkingEffort,
  setGlobalCustomValue,
  setGlobalIntensity,
} from '../ThinkingIntensityButton';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

/** Recognised as a reasoning model by name alone. */
const REASONING_MODEL = 'o3-mini';
const PLAIN_MODEL = 'gpt-4o';

function configureModel(model: string | null, supportsReasoning?: boolean) {
  const info: CustomModelInfo = {
    source: 'user',
    lastUpdated: '2026-01-01T00:00:00Z',
    supports_reasoning: supportsReasoning,
  };
  useProviderStore.setState({
    providers: [],
    customModelInfo: model && supportsReasoning !== undefined ? { [`acme/${model}`]: info } : {},
    defaultModelConfig: {
      ...getInitialDefaultModelConfig(),
      baseModel: { primary: model ? { providerId: 'acme', model } : null, fallback: null },
    },
  });
}

function renderButton() {
  return render(<ThinkingIntensityButton actionMode="agent" agentConfig={null} />);
}

async function openPopover(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /^Thinking Intensity/ }));
  return screen.findByRole('dialog');
}

async function openCustomField(user: ReturnType<typeof userEvent.setup>) {
  const dialog = await openPopover(user);
  await user.click(within(dialog).getByRole('button', { name: 'Custom' }));
  return screen.getByRole('textbox', { name: 'Custom' });
}

/** Storage the browser refuses to hand out: every access throws. */
function blockStorage() {
  const refuse = () => {
    throw new DOMException('blocked', 'SecurityError');
  };
  vi.stubGlobal('localStorage', { getItem: refuse, setItem: refuse, removeItem: refuse });
}

describe('ThinkingIntensityButton', () => {
  beforeEach(() => {
    // The tooltip arrow measures itself.
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    localStorage.clear();
    setGlobalIntensity('auto');
    configureModel(REASONING_MODEL);
  });

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
