import { beforeEach, describe, expect, it, vi } from 'vitest';

import { showSubsumptionUndoToast } from '@/hooks/globalEvents/subsumptionUndoToast';

const apiMocks = vi.hoisted(() => ({
  fetchWithTimeout: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: apiMocks.fetchWithTimeout,
}));

const NOTIFICATION = {
  status: 'notification',
  task_name: 'cognitive_subsumption',
  data: { count: 2, subsumed_ids: ['m1', 'm2'] },
};

describe('showSubsumptionUndoToast', () => {
  const t = (key: string) => key;
  const tIdle = (key: string, values?: Record<string, string | number>) => `${key}:${JSON.stringify(values)}`;
  const pushToast = { info: vi.fn(), success: vi.fn(), error: vi.fn() };
  const deps = { t, tIdle, pushToast };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers undo for a subsumption notification', () => {
    showSubsumptionUndoToast(NOTIFICATION, deps);

    expect(pushToast.info).toHaveBeenCalledWith(
      'cognitive_subsumption.notification:{"count":2}',
      expect.objectContaining({ action: expect.objectContaining({ label: 'undoConsolidation' }) }),
    );
  });

  it.each([
    ['other status', { ...NOTIFICATION, status: 'completed' }],
    ['other task', { ...NOTIFICATION, task_name: 'cognitive_derivation' }],
    ['zero count', { ...NOTIFICATION, data: { count: 0, subsumed_ids: ['m1'] } }],
    ['missing ids', { ...NOTIFICATION, data: { count: 2 } }],
  ])('ignores %s', (_label, data) => {
    showSubsumptionUndoToast(data, deps);

    expect(pushToast.info).not.toHaveBeenCalled();
  });

  it('posts the ids and reports success on undo', async () => {
    apiMocks.fetchWithTimeout.mockResolvedValue({ ok: true });
    showSubsumptionUndoToast(NOTIFICATION, deps);
    const { action } = pushToast.info.mock.calls[0][1];

    await action.onClick();

    expect(apiMocks.fetchWithTimeout).toHaveBeenCalledWith(
      '/memory/undo-consolidation',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ subsumed_ids: ['m1', 'm2'] }) }),
    );
    expect(pushToast.success).toHaveBeenCalledWith('undoConsolidationSuccess');
  });

  it('reports failure when the undo request is rejected', async () => {
    apiMocks.fetchWithTimeout.mockResolvedValue({ ok: false });
    showSubsumptionUndoToast(NOTIFICATION, deps);
    const { action } = pushToast.info.mock.calls[0][1];

    await action.onClick();

    expect(pushToast.error).toHaveBeenCalledWith('undoConsolidationFailed');
    expect(pushToast.success).not.toHaveBeenCalled();
  });
});
