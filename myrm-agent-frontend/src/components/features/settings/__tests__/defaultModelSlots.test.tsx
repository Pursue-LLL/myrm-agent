import { act, cleanup, fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DefaultModelConfig, ProviderConfig, SingleModelSelection } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';
import useRetrievalStore from '@/store/useRetrievalStore';

import { MODEL_SLOTS, type ModelSlotId } from '../default-model/modelSlots';
import { isSelectionUsable, useClearInvalidModelSelections } from '../default-model/useClearInvalidModelSelections';
import DefaultModelSection from '../sections/ai-core/DefaultModelSection';

const picked = vi.hoisted(() => ({ model: 'picked' }));

vi.mock('@/components/features/settings/default-model/EnabledModelSelect', () => ({
  default: (props: { value: unknown; onChange: (selection: { providerId: string; model: string } | null) => void }) => (
    <div data-testid="select" data-value={JSON.stringify(props.value)}>
      <button
        type="button"
        aria-label="pick"
        onClick={() => props.onChange({ providerId: 'p1', model: picked.model })}
      />
    </div>
  ),
}));
vi.mock('@/components/features/settings/sections/system/MediaGenerationSection', () => ({ default: () => null }));
vi.mock('@/hooks/useOrgModelPolicy', () => ({
  useOrgModelPolicy: () => ({ restricted: false, isModelAllowed: () => true }),
}));
vi.mock('@/services/memory/reindex', () => ({
  getMemoryOrphanEstimate: vi.fn(),
  startMemoryReindex: vi.fn(),
  getMemoryReindexStatus: vi.fn(),
}));

const SLOT_IDS = Object.keys(MODEL_SLOTS) as ModelSlotId[];

const sel = (model: string, providerId = 'p1'): SingleModelSelection => ({ providerId, model });
const provider = (overrides: Partial<ProviderConfig> = {}): ProviderConfig => ({
  id: 'p1',
  routingProfile: 'p1',
  name: 'Provider',
  isBuiltIn: true,
  isEnabled: true,
  apiKeys: [{ id: 'k', key: 'sk-test', remark: '', isActive: true }],
  apiUrl: '',
  enabledModels: [...SLOT_IDS, 'good-model'],
  availableModels: [],
  ...overrides,
});
const NONE = { primary: null, fallback: null };
const EMPTY: DefaultModelConfig = { baseModel: NONE, liteModel: NONE, fastModeModel: null, routingConfig: null };

function seed(providers: ProviderConfig[], config: DefaultModelConfig = EMPTY) {
  useProviderStore.setState({
    providers,
    defaultModelConfig: config,
    isInitialized: true,
    initError: null,
    initProviders: vi.fn(),
  });
}

/** Saves every slot as `p1/<slot id>` through the slot's own store action, with smart routing switched on. */
function fillEverySlot() {
  seed([provider()]);
  for (const slot of SLOT_IDS) {
    MODEL_SLOTS[slot].write(useProviderStore.getState())(sel(slot));
  }
  useProviderStore.getState().setRoutingEnabled(true);
}

const readSlots = () =>
  Object.fromEntries(
    SLOT_IDS.map((slot) => [slot, MODEL_SLOTS[slot].read(useProviderStore.getState().defaultModelConfig) ?? null]),
  );

beforeEach(() => {
  picked.model = 'picked';
  useRetrievalStore.setState({ checkOrphanCollections: vi.fn() });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('MODEL_SLOTS', () => {
  it.each(SLOT_IDS)('%s is stored in its own config field and nowhere else', (slot) => {
    seed([provider()]);

    MODEL_SLOTS[slot].write(useProviderStore.getState())(sel('chosen'));

    expect(readSlots()).toEqual(Object.fromEntries(SLOT_IDS.map((id) => [id, id === slot ? sel('chosen') : null])));
  });
});

describe('DefaultModelSection slot wiring', () => {
  it('shows every slot once, and each select reads and writes the slot it shows', () => {
    fillEverySlot();
    render(<DefaultModelSection />);

    const selects = screen.getAllByTestId('select');
    const shown = selects.map((el) => JSON.parse(el.dataset.value ?? 'null').model as ModelSlotId);
    expect([...shown].sort()).toEqual([...SLOT_IDS].sort());

    selects.forEach((select, index) => {
      const before = readSlots();
      picked.model = `picked-${index}`;
      fireEvent.click(within(select).getByRole('button', { name: 'pick' }));
      expect(readSlots()).toEqual({ ...before, [shown[index]]: sel(`picked-${index}`) });
    });
  });

  it('hides the routing tiers while smart routing is off', () => {
    fillEverySlot();
    useProviderStore.getState().setRoutingEnabled(false);
    render(<DefaultModelSection />);

    expect(screen.getAllByTestId('select')).toHaveLength(SLOT_IDS.length - 8);
  });

  it('retries the provider load from the error state', () => {
    const retryInit = vi.fn();
    useProviderStore.setState({ initError: 'offline', retryInit });
    render(<DefaultModelSection />);

    fireEvent.click(screen.getByRole('button'));

    expect(retryInit).toHaveBeenCalledTimes(1);
  });

  it('rings the routing card when opened with the focus deeplink', () => {
    vi.useFakeTimers();
    vi.mocked(Element.prototype.scrollIntoView).mockClear();
    window.history.pushState({}, '', '/?focus=routing');
    fillEverySlot();
    const { container } = render(<DefaultModelSection />);
    const card = container.querySelector('#smart-routing-section');

    vi.advanceTimersByTime(300);
    expect(card).toHaveClass('ring-2');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();

    vi.advanceTimersByTime(2500);
    expect(card).not.toHaveClass('ring-2');
    window.history.pushState({}, '', '/');
  });
});

describe('isSelectionUsable', () => {
  it.each<[string, SingleModelSelection | null, ProviderConfig, boolean]>([
    ['nothing is selected', null, provider(), true],
    ['the provider is unknown', sel('good-model', 'ghost'), provider(), false],
    ['the provider is disabled', sel('good-model'), provider({ isEnabled: false }), false],
    ['no API key is active', sel('good-model'), provider({ apiKeys: [] }), false],
    ['the model is no longer listed', sel('removed-model'), provider(), false],
    ['everything is in place', sel('good-model'), provider(), true],
  ])('when %s', (_case, selection, configured, usable) => {
    expect(isSelectionUsable([configured], selection)).toBe(usable);
  });
});

describe('useClearInvalidModelSelections', () => {
  const staleConfig: DefaultModelConfig = {
    baseModel: { primary: sel('good-model'), fallback: sel('removed-model') },
    liteModel: { primary: sel('good-model', 'ghost'), fallback: null },
    fastModeModel: null,
    routingConfig: {
      enabled: true,
      lightModel: { primary: sel('removed-model'), fallback: sel('good-model') },
      reasoningModel: NONE,
    },
    codeModel: { primary: sel('removed-model'), fallback: null },
  };

  it('clears the selections that cannot be used and keeps the others', () => {
    seed([provider()], staleConfig);

    renderHook(() => useClearInvalidModelSelections(true));

    expect(readSlots()).toMatchObject({
      base: sel('good-model'),
      baseFallback: null,
      lite: null,
      routingLight: null,
      routingLightFallback: sel('good-model'),
      code: null,
    });
  });

  it('waits for the provider config to load, then clears once', () => {
    seed([provider()], staleConfig);
    const { rerender } = renderHook(({ ready }) => useClearInvalidModelSelections(ready), {
      initialProps: { ready: false },
    });
    expect(readSlots().baseFallback).toEqual(sel('removed-model'));

    rerender({ ready: true });
    expect(readSlots().baseFallback).toBeNull();

    act(() => MODEL_SLOTS.baseFallback.write(useProviderStore.getState())(sel('removed-model')));
    rerender({ ready: true });
    expect(readSlots().baseFallback).toEqual(sel('removed-model'));
  });
});
