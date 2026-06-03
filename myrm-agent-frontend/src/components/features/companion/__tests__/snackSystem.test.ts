import { act, renderHook } from '@testing-library/react';

import useCompanionStore, { getEffectiveSnacks } from '@/store/useCompanionStore';

function getLocalDateKey(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

describe('Snack Reward System', () => {
  beforeEach(() => {
    const { result } = renderHook(() => useCompanionStore());
    act(() => {
      result.current.resetSession();
    });
    useCompanionStore.setState({
      snacksRemaining: 3,
      lastSnackReset: null,
      mascotXp: 0,
      mood: 'neutral',
    });
  });

  it('initializes with 3 snacks', () => {
    const { snacksRemaining } = useCompanionStore.getState();
    expect(snacksRemaining).toBe(3);
  });

  it('feedSnack decrements remaining and adds XP', () => {
    const store = useCompanionStore.getState();
    const ok = store.feedSnack();
    expect(ok).toBe(true);
    const after = useCompanionStore.getState();
    expect(after.snacksRemaining).toBe(2);
    expect(after.mascotXp).toBe(10);
    expect(after.mood).toBe('happy');
  });

  it('feedSnack returns false when no snacks left', () => {
    const today = getLocalDateKey();
    useCompanionStore.setState({ snacksRemaining: 0, lastSnackReset: today });
    const store = useCompanionStore.getState();
    const ok = store.feedSnack();
    expect(ok).toBe(false);
    expect(useCompanionStore.getState().mascotXp).toBe(0);
  });

  it('feedSnack resets to 3 on new day', () => {
    useCompanionStore.setState({ snacksRemaining: 0, lastSnackReset: '2020-01-01' });
    const store = useCompanionStore.getState();
    const ok = store.feedSnack();
    expect(ok).toBe(true);
    const after = useCompanionStore.getState();
    expect(after.snacksRemaining).toBe(2);
    expect(after.lastSnackReset).toBe(getLocalDateKey());
  });

  it('allows exactly 3 feeds per day', () => {
    const store = useCompanionStore.getState();
    expect(store.feedSnack()).toBe(true);
    expect(store.feedSnack()).toBe(true);
    expect(store.feedSnack()).toBe(true);
    expect(store.feedSnack()).toBe(false);
    expect(useCompanionStore.getState().snacksRemaining).toBe(0);
    expect(useCompanionStore.getState().mascotXp).toBe(30);
  });

  it('updates lastInteractionAt on feed', () => {
    const before = useCompanionStore.getState().lastInteractionAt;
    useCompanionStore.getState().feedSnack();
    const after = useCompanionStore.getState().lastInteractionAt;
    expect(after).not.toBeNull();
    expect(after).not.toBe(before);
  });

  it('persists snack state via lastSnackReset', () => {
    useCompanionStore.getState().feedSnack();
    const state = useCompanionStore.getState();
    expect(state.snacksRemaining).toBe(2);
    expect(state.lastSnackReset).toBe(getLocalDateKey());
  });

  it('getEffectiveSnacks returns 3 for null lastSnackReset', () => {
    expect(getEffectiveSnacks(0, null)).toBe(3);
  });

  it('getEffectiveSnacks returns 3 for stale date', () => {
    expect(getEffectiveSnacks(0, '2020-01-01')).toBe(3);
  });

  it('getEffectiveSnacks returns actual remaining for today', () => {
    const today = getLocalDateKey();
    expect(getEffectiveSnacks(1, today)).toBe(1);
  });

  it('getEffectiveSnacks returns 0 when today and depleted', () => {
    const today = getLocalDateKey();
    expect(getEffectiveSnacks(0, today)).toBe(0);
  });

  it('feedSnack does not change mood when depleted', () => {
    const today = getLocalDateKey();
    useCompanionStore.setState({ snacksRemaining: 0, lastSnackReset: today, mood: 'neutral' });
    useCompanionStore.getState().feedSnack();
    expect(useCompanionStore.getState().mood).toBe('neutral');
  });

  it('feedSnack accumulates XP correctly across feeds', () => {
    useCompanionStore.setState({ mascotXp: 50 });
    useCompanionStore.getState().feedSnack();
    expect(useCompanionStore.getState().mascotXp).toBe(60);
    useCompanionStore.getState().feedSnack();
    expect(useCompanionStore.getState().mascotXp).toBe(70);
  });
});
