/**
 * The thinking slider and the intensity button sit side by side in the composer options and share one intensity:
 * what one chooses the other shows, and switching models brings back what was saved for the new model.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ThinkingIntensityButton, {
  getThinkingEffort,
  setGlobalIntensity,
} from '@/components/features/message-input-actions/ThinkingIntensityButton';
import { getInitialDefaultModelConfig } from '@/store/config/providerTypes';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import ThinkingBudgetEffortSlider from '../ThinkingBudgetEffortSlider';
import { useThinkingBudgetStore } from '../useThinkingBudgetStore';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

function selectModel(model: string) {
  useProviderStore.setState({
    providers: [],
    customModelInfo: {},
    defaultModelConfig: {
      ...getInitialDefaultModelConfig(),
      baseModel: { primary: { providerId: 'acme', model }, fallback: null },
    },
  });
}

function renderControls() {
  return render(
    <>
      <ThinkingBudgetEffortSlider />
      <ThinkingIntensityButton actionMode="agent" agentConfig={null} />
    </>,
  );
}

describe('thinking slider and intensity button together', () => {
  beforeEach(() => {
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
    useThinkingBudgetStore.setState({ level: 'auto', currentModel: '', tokenBudget: 0, reasoningEffort: undefined });
    useChatStore.setState({ actionMode: 'agent', agentConfig: null });
    selectModel('o3-mini');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('brings back what the button saved for the model switched to, though the slider never saw it', () => {
    localStorage.setItem('thinkingIntensity_o3-mini', 'high');
    localStorage.setItem('thinkingIntensity_o4-mini', 'max');
    renderControls();
    expect(getThinkingEffort()).toBe('high');

    act(() => selectModel('o4-mini'));

    expect(getThinkingEffort()).toBe('max');
    expect(localStorage.getItem('thinkingIntensity_o4-mini')).toBe('max');
    expect(screen.getByRole('button', { name: 'Thinking Intensity: Max' })).toBeInTheDocument();
  });

  it('brings back a custom value the button saved for the model switched to', () => {
    localStorage.setItem('thinkingIntensity_o3-mini', 'high');
    localStorage.setItem('thinkingIntensityCustom_o4-mini', '24k');
    renderControls();

    act(() => selectModel('o4-mini'));

    expect(getThinkingEffort()).toBe('24k');
    expect(localStorage.getItem('thinkingIntensityCustom_o4-mini')).toBe('24k');
  });

  it('shows a level chosen on the slider in the button and saves it for the model', () => {
    renderControls();

    fireEvent.click(screen.getByTestId('thinking-step-medium'));

    expect(getThinkingEffort()).toBe('medium');
    expect(screen.getByRole('button', { name: 'Thinking Intensity: Medium' })).toBeInTheDocument();
    expect(localStorage.getItem('thinkingIntensity_o3-mini')).toBe('medium');
    expect(localStorage.getItem('myrm_thinking_budget_o3-mini')).toBe('medium');
  });

  it('restores what the slider saved for a model on the next visit', () => {
    localStorage.setItem('thinkingIntensity_o3-mini', 'low');
    localStorage.setItem('myrm_thinking_budget_o3-mini', 'low');

    renderControls();

    expect(getThinkingEffort()).toBe('low');
    expect(screen.getByRole('button', { name: 'Thinking Intensity: Low' })).toBeInTheDocument();
  });
});
