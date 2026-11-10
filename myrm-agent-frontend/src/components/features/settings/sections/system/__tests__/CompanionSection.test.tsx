import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { evolveStats, generateCompanion, HATS, SPECIES } from '@/components/features/companion/companionGenerator';
import type { Rarity } from '@/components/features/companion/companionGenerator';
import { deferred } from '@/test-utils/deferred';

import CompanionSection from '../CompanionSection';

interface EvolutionStatus {
  metrics: { conversations: number; active_days: number; total_messages: number };
  current_rarity: string;
  max_reachable_rarity: string;
  can_evolve: boolean;
  next_threshold: { conversations: number; active_days: number; total_messages: number } | null;
}

const USER_ID = 'user-1';
const bones = generateCompanion(USER_ID);

const kit = vi.hoisted(() => ({
  apiRequest: vi.fn<(path: string, options?: { silent?: boolean }) => Promise<unknown>>(),
  userId: undefined as string | undefined,
  store: {} as Record<string, unknown> & { evolvedRarity: string | null; evolvedAt: number | null },
  refresh: (() => undefined) as () => void,
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/lib/api', () => ({ apiRequest: kit.apiRequest }));
vi.mock('@/store/useAuthStore', () => ({
  default: (select: (state: { user: { id: string } | null }) => unknown) =>
    select({ user: kit.userId ? { id: kit.userId } : null }),
}));
// A store update re-renders its readers; `kit.refresh()` plays that part after a test edits `kit.store`.
vi.mock('@/store/useCompanionStore', async () => {
  const { useReducer } = await import('react');
  return {
    default: function useCompanionStore() {
      const [, refresh] = useReducer((renders: number) => renders + 1, 0);
      kit.refresh = refresh;
      return kit.store;
    },
  };
});

// The server answers with the status itself, not wrapped in an envelope.
const status = (overrides: Partial<EvolutionStatus> = {}): EvolutionStatus => ({
  metrics: { conversations: 3, active_days: 2, total_messages: 40 },
  current_rarity: 'Common',
  max_reachable_rarity: 'Common',
  can_evolve: false,
  next_threshold: { conversations: 10, active_days: 5, total_messages: 100 },
  ...overrides,
});

const actions = () => kit.store as Record<string, ReturnType<typeof vi.fn>>;
const evolveButton = () => screen.getByRole('button', { name: 'Evolve!' });
const nameInput = () => screen.getByRole('textbox');

async function renderSection(state: Record<string, unknown> = {}) {
  Object.assign(kit.store, state);
  const view = render(<CompanionSection />);
  await act(async () => undefined);
  return view;
}

beforeEach(() => {
  vi.resetAllMocks();
  kit.userId = USER_ID;
  kit.apiRequest.mockResolvedValue(status());
  kit.store = {
    enabled: true,
    muted: false,
    nameOverride: null,
    speciesOverride: null,
    hatOverride: undefined,
    evolvedRarity: 'Common',
    evolvedAt: null,
    setEnabled: vi.fn(),
    setMuted: vi.fn(),
    setNameOverride: vi.fn(),
    setSpeciesOverride: vi.fn(),
    setHatOverride: vi.fn(),
    // The real store records the new rarity, which makes the section ask for the status of that rarity.
    evolve: vi.fn((rarity: Rarity) => {
      kit.store.evolvedRarity = rarity;
      kit.store.evolvedAt = 1;
    }),
    loadConfigFromServer: vi.fn(),
    saveConfigToServer: vi.fn(),
  };
});

afterEach(() => {
  vi.useRealTimers();
});

describe('CompanionSection without a user', () => {
  it('renders nothing and asks for nothing', async () => {
    kit.userId = undefined;

    const { container } = await renderSection();

    expect(container).toBeEmptyDOMElement();
    expect(kit.apiRequest).not.toHaveBeenCalled();
  });
});

describe('CompanionSection evolution status', () => {
  it('asks quietly for the status of the displayed rarity', async () => {
    await renderSection({ evolvedRarity: 'Rare' });

    expect(kit.apiRequest).toHaveBeenCalledExactlyOnceWith('/companion/evolution-status?current_rarity=Rare', {
      silent: true,
    });
  });

  it('shows the progress toward the next level from the status the server sends', async () => {
    await renderSection();

    expect(screen.getByText('Progress to Next')).toBeInTheDocument();
    expect(screen.getByText('3 / 10')).toBeInTheDocument();
    expect(screen.getByText('2 / 5')).toBeInTheDocument();
    expect(screen.getByText('40 / 100')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Evolve!' })).toBeNull();
  });

  it('offers the evolution once it has been earned and evolves one level', async () => {
    kit.apiRequest.mockResolvedValue(status({ can_evolve: true, max_reachable_rarity: 'Uncommon' }));
    const user = userEvent.setup();
    await renderSection();

    await user.click(evolveButton());

    expect(actions().evolve).toHaveBeenCalledExactlyOnceWith(
      'Uncommon',
      evolveStats(bones.stats, bones.peakStat, USER_ID, 'Uncommon'),
    );
    expect(screen.getByText(/evolved to/)).toBeInTheDocument();
  });

  it('celebrates the evolution for a moment', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    kit.apiRequest.mockResolvedValue(status({ can_evolve: true, max_reachable_rarity: 'Uncommon' }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await renderSection();

    await user.click(evolveButton());
    expect(screen.getByText(/evolved to/)).toBeInTheDocument();

    await act(async () => vi.advanceTimersByTimeAsync(3000));
    expect(screen.queryByText(/evolved to/)).toBeNull();
  });

  it('still offers the evolution when the level it leads to is the last one', async () => {
    kit.apiRequest.mockResolvedValue(
      status({ can_evolve: true, max_reachable_rarity: 'Legendary', next_threshold: null }),
    );
    await renderSection();

    expect(evolveButton()).toBeInTheDocument();
    expect(screen.queryByText('Progress to Next')).toBeNull();
  });

  it('withdraws the offer right after evolving, then reads the status of the new rarity', async () => {
    kit.apiRequest.mockResolvedValueOnce(status({ can_evolve: true, max_reachable_rarity: 'Rare' }));
    const user = userEvent.setup();
    await renderSection();
    const next = deferred<EvolutionStatus>();
    kit.apiRequest.mockReturnValueOnce(next.promise);

    await user.click(evolveButton());

    expect(screen.queryByRole('button', { name: 'Evolve!' })).toBeNull();
    expect(kit.apiRequest).toHaveBeenLastCalledWith('/companion/evolution-status?current_rarity=Uncommon', {
      silent: true,
    });

    await act(async () => next.resolve(status({ can_evolve: true, max_reachable_rarity: 'Rare' })));
    expect(evolveButton()).toBeInTheDocument();
    expect(actions().evolve).toHaveBeenCalledTimes(1);
  });

  it('ignores a status that arrives after the displayed rarity has changed', async () => {
    const stale = deferred<EvolutionStatus>();
    kit.apiRequest.mockReturnValueOnce(stale.promise);
    await renderSection();
    kit.apiRequest.mockResolvedValueOnce(
      status({
        max_reachable_rarity: 'Rare',
        next_threshold: { conversations: 30, active_days: 10, total_messages: 300 },
      }),
    );

    // The stored settings finish loading and move the companion to a higher rarity while the first request is out.
    await act(async () => {
      Object.assign(kit.store, { evolvedRarity: 'Rare', evolvedAt: 5 });
      kit.refresh();
    });
    await act(async () => stale.resolve(status({ can_evolve: true, max_reachable_rarity: 'Uncommon' })));

    expect(screen.getByText('3 / 30')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Evolve!' })).toBeNull();
  });

  it('shows no evolution controls at the top level', async () => {
    kit.apiRequest.mockResolvedValue(status({ can_evolve: true, next_threshold: null }));

    await renderSection({ evolvedRarity: 'Legendary' });

    expect(screen.getByText('Max Level Reached')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Evolve!' })).toBeNull();
  });

  it('stays quiet and shows no numbers when the status cannot be read', async () => {
    kit.apiRequest.mockRejectedValue(new Error('offline'));

    await renderSection();

    expect(screen.getByText('Evolution')).toBeInTheDocument();
    expect(screen.queryByText('Progress to Next')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Evolve!' })).toBeNull();
  });

  it('hides the evolution panel and asks nothing while the companion is off', async () => {
    await renderSection({ enabled: false });

    expect(screen.queryByText('Evolution')).toBeNull();
    expect(kit.apiRequest).not.toHaveBeenCalled();
  });
});

describe('CompanionSection settings', () => {
  it('loads the stored settings once and writes nothing back until the user edits', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    await renderSection();
    await act(async () => vi.advanceTimersByTimeAsync(2000));

    expect(actions().loadConfigFromServer).toHaveBeenCalledTimes(1);
    expect(actions().saveConfigToServer).not.toHaveBeenCalled();
  });

  it('saves one edit session once, after typing pauses', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await renderSection();

    await user.type(nameInput(), 'ab');
    expect(actions().setNameOverride).toHaveBeenCalledTimes(2);
    expect(actions().saveConfigToServer).not.toHaveBeenCalled();

    await act(async () => vi.advanceTimersByTimeAsync(500));
    expect(actions().saveConfigToServer).toHaveBeenCalledTimes(1);
  });

  it('flushes a pending edit when the user leaves before it was saved', async () => {
    const user = userEvent.setup();
    const { unmount } = await renderSection();
    await user.type(nameInput(), 'a');
    expect(actions().saveConfigToServer).not.toHaveBeenCalled();

    unmount();

    expect(actions().saveConfigToServer).toHaveBeenCalledTimes(1);
  });

  it('does not save again on leaving once the edit has been saved', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { unmount } = await renderSection();
    await user.type(nameInput(), 'a');
    await act(async () => vi.advanceTimersByTimeAsync(500));
    expect(actions().saveConfigToServer).toHaveBeenCalledTimes(1);

    unmount();

    expect(actions().saveConfigToServer).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['a name', () => userEvent.type(nameInput(), 'a')],
    ['a species', () => userEvent.click(screen.getByRole('button', { name: SPECIES[0] }))],
    ['a hat', () => userEvent.click(screen.getByRole('button', { name: HATS[0] }))],
  ])('schedules a save when the user changes %s', async (_what, edit) => {
    const { unmount } = await renderSection();

    await edit();
    expect(actions().saveConfigToServer).not.toHaveBeenCalled();
    unmount();

    expect(actions().saveConfigToServer).toHaveBeenCalledTimes(1);
  });

  it('saves nothing when the user leaves without editing', async () => {
    const { unmount } = await renderSection();

    unmount();

    expect(actions().saveConfigToServer).not.toHaveBeenCalled();
  });

  it('shows the chosen name, falling back to the generated one, and clears an emptied name', async () => {
    const user = userEvent.setup();
    const { unmount } = await renderSection();
    expect(nameInput()).toHaveValue(bones.defaultName);
    unmount();

    await renderSection({ nameOverride: 'Rex' });
    expect(nameInput()).toHaveValue('Rex');
    await user.clear(nameInput());

    expect(actions().setNameOverride).toHaveBeenLastCalledWith(null);
  });

  it('picks a species, and going back to the generated one drops the override', async () => {
    const user = userEvent.setup();
    const other = SPECIES.find((species) => species !== bones.species) ?? bones.species;
    await renderSection();

    await user.click(screen.getByRole('button', { name: other }));
    expect(actions().setSpeciesOverride).toHaveBeenLastCalledWith(other);

    await user.click(screen.getByRole('button', { name: bones.species }));
    expect(actions().setSpeciesOverride).toHaveBeenLastCalledWith(null);
  });

  it('chooses between the generated hat, no hat and a specific hat', async () => {
    const user = userEvent.setup();
    await renderSection();

    await user.click(screen.getByRole('button', { name: 'None' }));
    expect(actions().setHatOverride).toHaveBeenLastCalledWith(null);

    await user.click(screen.getByRole('button', { name: HATS[0] }));
    expect(actions().setHatOverride).toHaveBeenLastCalledWith(HATS[0]);

    await user.click(screen.getByRole('button', { name: 'Default' }));
    expect(actions().setHatOverride).toHaveBeenLastCalledWith(undefined);
  });

  it('turns the companion on and off, and only lets it be muted while it is on', async () => {
    const user = userEvent.setup();
    const { unmount } = await renderSection();
    const [enable, mute] = screen.getAllByRole('switch');

    await user.click(enable);
    expect(actions().setEnabled).toHaveBeenCalledWith(false);
    await user.click(mute);
    expect(actions().setMuted).toHaveBeenCalledWith(true);
    unmount();

    await renderSection({ enabled: false });
    expect(screen.getAllByRole('switch')[1]).toBeDisabled();
    expect(nameInput()).toBeDisabled();
  });
});
