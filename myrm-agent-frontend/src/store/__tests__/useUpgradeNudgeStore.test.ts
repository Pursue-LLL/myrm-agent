import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { useUpgradeNudgeStore } from '@/store/useUpgradeNudgeStore';

vi.mock('@/store/useBudgetExceededStore', () => ({
  useBudgetExceededStore: { getState: () => ({ open: false }) },
}));

const STORAGE_KEY = 'upgrade_nudge_dismissed_at';

describe('useUpgradeNudgeStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useUpgradeNudgeStore.setState({ open: false, trigger: null, blockedFeature: null });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('showLowBalance', () => {
    it('opens dialog when not recently dismissed', () => {
      useUpgradeNudgeStore.getState().showLowBalance(100, 600);
      const state = useUpgradeNudgeStore.getState();
      expect(state.open).toBe(true);
      expect(state.trigger).toBe('low_balance');
      expect(state.blockedFeature).toBeNull();
    });

    it('does NOT open when dismissed within 24h', () => {
      localStorage.setItem(STORAGE_KEY, String(Date.now()));
      useUpgradeNudgeStore.getState().showLowBalance(100, 600);
      expect(useUpgradeNudgeStore.getState().open).toBe(false);
    });

    it('opens when dismissal is older than 24h', () => {
      const expired = Date.now() - 25 * 60 * 60 * 1000;
      localStorage.setItem(STORAGE_KEY, String(expired));
      useUpgradeNudgeStore.getState().showLowBalance(100, 600);
      expect(useUpgradeNudgeStore.getState().open).toBe(true);
    });
  });

  describe('showFeatureGate', () => {
    it('opens dialog with feature name', () => {
      useUpgradeNudgeStore.getState().showFeatureGate('cron');
      const state = useUpgradeNudgeStore.getState();
      expect(state.open).toBe(true);
      expect(state.trigger).toBe('feature_gate');
      expect(state.blockedFeature).toBe('cron');
    });

    it('opens even when recently dismissed (P1 fix)', () => {
      localStorage.setItem(STORAGE_KEY, String(Date.now()));
      useUpgradeNudgeStore.getState().showFeatureGate('ingress');
      expect(useUpgradeNudgeStore.getState().open).toBe(true);
      expect(useUpgradeNudgeStore.getState().blockedFeature).toBe('ingress');
    });
  });

  describe('close', () => {
    it('closes dialog and writes dismissal timestamp', () => {
      useUpgradeNudgeStore.setState({ open: true, trigger: 'low_balance', blockedFeature: null });
      useUpgradeNudgeStore.getState().close();
      const state = useUpgradeNudgeStore.getState();
      expect(state.open).toBe(false);
      expect(state.trigger).toBeNull();
      expect(state.blockedFeature).toBeNull();
      const ts = localStorage.getItem(STORAGE_KEY);
      expect(ts).not.toBeNull();
      expect(Date.now() - parseInt(ts!, 10)).toBeLessThan(1000);
    });
  });

  describe('mutual exclusion with BudgetExceededDialog', () => {
    it('does NOT open when BudgetExceededDialog is open', async () => {
      const mod = await import('@/store/useBudgetExceededStore');
      const original = mod.useBudgetExceededStore.getState;
      mod.useBudgetExceededStore.getState = () => ({ open: true }) as ReturnType<typeof original>;

      useUpgradeNudgeStore.getState().showLowBalance(100, 600);
      expect(useUpgradeNudgeStore.getState().open).toBe(false);

      useUpgradeNudgeStore.getState().showFeatureGate('cron');
      expect(useUpgradeNudgeStore.getState().open).toBe(false);

      mod.useBudgetExceededStore.getState = original;
    });
  });
});
