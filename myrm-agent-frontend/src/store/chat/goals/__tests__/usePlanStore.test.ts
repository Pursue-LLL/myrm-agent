import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePlanStore } from '../usePlanStore';

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(),
}));

function makePlan(statuses: Array<'pending' | 'in_progress' | 'completed' | 'skipped'> = ['pending']) {
  return {
    goal: 'Test goal',
    reasoning: '',
    steps: statuses.map((status, i) => ({
      step_id: `step_${i}`,
      description: `Step ${i}`,
      expected_output: '',
      status,
      dependencies: [],
    })),
  };
}

describe('usePlanStore', () => {
  beforeEach(() => {
    usePlanStore.setState({ plan: null, isLoading: false });
  });

  describe('clearPlan', () => {
    it('sets plan to null', () => {
      usePlanStore.setState({ plan: makePlan() });
      expect(usePlanStore.getState().plan).not.toBeNull();

      usePlanStore.getState().clearPlan();
      expect(usePlanStore.getState().plan).toBeNull();
    });

    it('is no-op when plan is already null', () => {
      usePlanStore.getState().clearPlan();
      expect(usePlanStore.getState().plan).toBeNull();
    });
  });

  describe('clearActivePlan', () => {
    it('clears plan when steps contain pending items', () => {
      usePlanStore.setState({ plan: makePlan(['completed', 'pending']) });
      usePlanStore.getState().clearActivePlan();
      expect(usePlanStore.getState().plan).toBeNull();
    });

    it('clears plan when steps contain in_progress items', () => {
      usePlanStore.setState({ plan: makePlan(['in_progress', 'completed']) });
      usePlanStore.getState().clearActivePlan();
      expect(usePlanStore.getState().plan).toBeNull();
    });

    it('preserves plan when all steps are completed/skipped', () => {
      const plan = makePlan(['completed', 'skipped', 'completed']);
      usePlanStore.setState({ plan });
      usePlanStore.getState().clearActivePlan();
      expect(usePlanStore.getState().plan).toEqual(plan);
    });

    it('is no-op when plan is null', () => {
      usePlanStore.getState().clearActivePlan();
      expect(usePlanStore.getState().plan).toBeNull();
    });
  });

  describe('fetchPlan stale response guard', () => {
    let fetchMock: ReturnType<typeof vi.fn>;

    beforeEach(async () => {
      const api = await import('@/lib/api');
      fetchMock = api.fetchWithTimeout as ReturnType<typeof vi.fn>;
      fetchMock.mockReset();
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('updates plan on successful fetch', async () => {
      const plan = makePlan(['pending']);
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ plan }),
      });

      await usePlanStore.getState().fetchPlan('chat-1');
      expect(usePlanStore.getState().plan).toEqual(plan);
      expect(usePlanStore.getState().isLoading).toBe(false);
    });

    it('discards stale response when newer fetch is issued', async () => {
      const stalePlan = makePlan(['pending']);
      const freshPlan = makePlan(['in_progress']);

      let resolveStale: (v: unknown) => void;
      const stalePromise = new Promise((r) => { resolveStale = r; });

      fetchMock
        .mockReturnValueOnce(stalePromise)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ plan: freshPlan }) });

      const staleCall = usePlanStore.getState().fetchPlan('chat-1');
      const freshCall = usePlanStore.getState().fetchPlan('chat-2');

      await freshCall;
      expect(usePlanStore.getState().plan).toEqual(freshPlan);

      resolveStale!({ ok: true, json: async () => ({ plan: stalePlan }) });
      await staleCall;

      expect(usePlanStore.getState().plan).toEqual(freshPlan);
    });

    it('does not update isLoading from stale call', async () => {
      let resolveStale: (v: unknown) => void;
      const stalePromise = new Promise((r) => { resolveStale = r; });

      fetchMock
        .mockReturnValueOnce(stalePromise)
        .mockResolvedValueOnce({ ok: true, json: async () => ({ plan: null }) });

      const staleCall = usePlanStore.getState().fetchPlan('chat-1');
      await usePlanStore.getState().fetchPlan('chat-2');

      expect(usePlanStore.getState().isLoading).toBe(false);

      resolveStale!({ ok: true, json: async () => ({ plan: makePlan() }) });
      await staleCall;

      expect(usePlanStore.getState().isLoading).toBe(false);
    });

    it('handles fetch error gracefully', async () => {
      fetchMock.mockRejectedValueOnce(new Error('Network error'));
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await usePlanStore.getState().fetchPlan('chat-1');

      expect(usePlanStore.getState().plan).toBeNull();
      expect(usePlanStore.getState().isLoading).toBe(false);
      consoleSpy.mockRestore();
    });

    it('handles non-200 response without crashing', async () => {
      fetchMock.mockResolvedValueOnce({ ok: false, status: 404 });

      await usePlanStore.getState().fetchPlan('chat-1');

      expect(usePlanStore.getState().plan).toBeNull();
      expect(usePlanStore.getState().isLoading).toBe(false);
    });

    it('handles response with null plan field', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ plan: null }),
      });

      await usePlanStore.getState().fetchPlan('chat-1');

      expect(usePlanStore.getState().plan).toBeNull();
      expect(usePlanStore.getState().isLoading).toBe(false);
    });
  });

  describe('updateStepStatus', () => {
    it('updates matching step status', () => {
      usePlanStore.setState({
        plan: makePlan(['pending', 'pending']),
      });

      usePlanStore.getState().updateStepStatus('step_0', 'completed');
      expect(usePlanStore.getState().plan?.steps[0].status).toBe('completed');
      expect(usePlanStore.getState().plan?.steps[1].status).toBe('pending');
    });

    it('does nothing when plan is null', () => {
      usePlanStore.getState().updateStepStatus('step_0', 'completed');
      expect(usePlanStore.getState().plan).toBeNull();
    });

    it('does nothing for non-matching step id', () => {
      usePlanStore.setState({ plan: makePlan(['pending']) });
      usePlanStore.getState().updateStepStatus('nonexistent', 'completed');
      expect(usePlanStore.getState().plan?.steps[0].status).toBe('pending');
    });
  });
});
