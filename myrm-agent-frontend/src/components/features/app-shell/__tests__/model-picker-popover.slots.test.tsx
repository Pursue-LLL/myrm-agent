import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ModelPickerPopover from '../model-picker-popover';

const state = vi.hoisted(() => ({ restricted: false }));

const PROVIDERS = [
  { id: 'p1', name: 'Provider One', isEnabled: true, enabledModels: ['model-a'], providerType: 'openai' },
  { id: 'ollama', name: 'Ollama', isEnabled: true, enabledModels: ['llama3'], providerType: 'ollama' },
];
const ENABLED_MODELS = [
  { providerId: 'p1', providerName: 'Provider One', model: 'model-a' },
  { providerId: 'ollama', providerName: 'Ollama', model: 'llama3' },
];

vi.mock('@/store/useProviderStore', () => ({
  default: () => ({ providers: PROVIDERS, getEnabledModels: () => ENABLED_MODELS, customModelInfo: {} }),
}));
vi.mock('@/store/useOrgModelPolicyStore', () => ({
  useOrgModelPolicyStore: () => ({
    restricted: state.restricted,
    initialized: true,
    loadPolicy: vi.fn(),
    isModelAllowed: (name: string) => name.startsWith('ollama/'),
  }),
}));
vi.mock('@/components/features/settings/model-service/ProviderIcon', () => ({ default: () => null }));
vi.mock('@/components/features/app-shell/capability-icons', () => ({ default: () => null }));
vi.mock('@/services/llm-config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/llm-config')>()),
  fetchModelCapabilitiesBatch: vi.fn().mockResolvedValue({}),
  fetchModelSwitchPreflight: vi.fn().mockResolvedValue({}),
}));
vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

type PickerProps = ComponentProps<typeof ModelPickerPopover>;

function renderPicker(props: Partial<PickerProps> = {}) {
  const handlers = {
    onSelect: vi.fn(),
    onSelectFallback: vi.fn(),
    onClearFallback: vi.fn(),
    onSelectSafetyFallback: vi.fn(),
    onClearSafetyFallback: vi.fn(),
    onSelectMoaPreset: vi.fn(),
    onSelectSmartRouting: vi.fn(),
  };
  render(
    <ModelPickerPopover
      trigger={<button type="button">open</button>}
      currentSelection={{ providerId: 'p1', model: 'model-a' }}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

const item = (providerId: string, model: string) => screen.getByTestId(`model-item-${providerId}-${model}`);
/** The clear buttons sit inside the tab buttons, so only buttons without a nested button count. */
const clearButtons = () =>
  screen
    .getAllByRole('button')
    .filter((button) => button.querySelector('svg.lucide-x') && !button.querySelector('button'));

beforeEach(() => {
  state.restricted = false;
});

describe('ModelPickerPopover slot tabs', () => {
  it('shows the slot tabs only when a fallback handler is supplied', () => {
    renderPicker({ onSelectFallback: undefined });
    expect(screen.queryByText('fallbackSlot')).not.toBeInTheDocument();
  });

  it('offers the Safety tab only when a safety handler is supplied', () => {
    renderPicker({ onSelectSafetyFallback: undefined });
    expect(screen.getByText('fallbackSlot')).toBeInTheDocument();
    expect(screen.queryByText('Safety')).not.toBeInTheDocument();
  });

  it('routes a model click to the active slot handler', () => {
    const handlers = renderPicker();

    fireEvent.click(item('ollama', 'llama3'));
    expect(handlers.onSelect).toHaveBeenCalledWith('ollama', 'llama3');

    fireEvent.click(screen.getByText('fallbackSlot'));
    fireEvent.click(item('p1', 'model-a'));
    expect(handlers.onSelectFallback).toHaveBeenCalledWith('p1', 'model-a');

    fireEvent.click(screen.getByText('Safety'));
    fireEvent.click(item('ollama', 'llama3'));
    expect(handlers.onSelectSafetyFallback).toHaveBeenCalledWith('ollama', 'llama3');
    expect(handlers.onSelect).toHaveBeenCalledTimes(1);
  });

  it('shows the selection of each slot with a destructive-text clear button that does not switch tabs', () => {
    const handlers = renderPicker({
      fallbackSelection: { providerId: 'ollama', model: 'llama3' },
      safetyFallbackSelection: { providerId: 'p1', model: 'model-a' },
    });

    const [clearFallback, clearSafety] = clearButtons();
    expect(clearFallback).toHaveClass('hover:text-destructive-text');
    expect(clearSafety).toHaveClass('hover:text-destructive-text');

    fireEvent.click(clearFallback);
    fireEvent.click(clearSafety);

    expect(handlers.onClearFallback).toHaveBeenCalledTimes(1);
    expect(handlers.onClearSafetyFallback).toHaveBeenCalledTimes(1);
    fireEvent.click(item('ollama', 'llama3'));
    expect(handlers.onSelect).toHaveBeenCalledWith('ollama', 'llama3');
    expect(handlers.onSelectFallback).not.toHaveBeenCalled();
  });

  it('marks empty fallback slots as not set', () => {
    renderPicker({ safetyFallbackSelection: null, fallbackSelection: null });

    expect(screen.getAllByText('notSet')).toHaveLength(2);
    expect(clearButtons()).toHaveLength(0);
  });
});

describe('ModelPickerPopover list sections', () => {
  const moaPresets = [{ id: 'quality', label: 'Quality', refCount: 3 }];

  it('toggles a MoA preset: selecting the active one clears it', () => {
    const handlers = renderPicker({ moaPresets, activeMoaPresetId: 'quality' });

    fireEvent.click(screen.getByText('Quality'));
    expect(handlers.onSelectMoaPreset).toHaveBeenCalledWith(null);
  });

  it('selects an inactive MoA preset', () => {
    const handlers = renderPicker({ moaPresets, activeMoaPresetId: null });

    fireEvent.click(screen.getByText('Quality'));
    expect(handlers.onSelectMoaPreset).toHaveBeenCalledWith('quality');
  });

  it('hides the MoA group and smart routing outside the primary slot', () => {
    renderPicker({ moaPresets, isSmartRoutingAvailable: true });
    expect(screen.getByText('Quality')).toBeInTheDocument();
    expect(screen.getByTestId('smart-routing-option')).toBeInTheDocument();

    fireEvent.click(screen.getByText('fallbackSlot'));

    expect(screen.queryByText('Quality')).not.toBeInTheDocument();
    expect(screen.queryByTestId('smart-routing-option')).not.toBeInTheDocument();
  });

  it('filters the list with the search box and reports an empty result', () => {
    renderPicker();
    const search = screen.getByPlaceholderText('searchModels');

    fireEvent.change(search, { target: { value: 'llama' } });
    expect(screen.queryByTestId('model-item-p1-model-a')).not.toBeInTheDocument();
    expect(item('ollama', 'llama3')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'nothing-matches' } });
    expect(screen.getByText('noMatchingModels')).toBeInTheDocument();
  });

  it('disables models blocked by the organisation policy', () => {
    state.restricted = true;
    const handlers = renderPicker();

    expect(item('p1', 'model-a')).toBeDisabled();
    expect(item('p1', 'model-a')).toHaveAttribute('title', 'orgPolicyRestricted');
    fireEvent.click(item('p1', 'model-a'));
    expect(handlers.onSelect).not.toHaveBeenCalled();

    fireEvent.click(item('ollama', 'llama3'));
    expect(handlers.onSelect).toHaveBeenCalledWith('ollama', 'llama3');
  });
});
