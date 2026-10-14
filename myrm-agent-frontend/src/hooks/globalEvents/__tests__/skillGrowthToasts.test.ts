import { beforeEach, describe, expect, it, vi } from 'vitest';

import { showSkillEvolvedToast, showSkillLearnedToast } from '@/hooks/globalEvents/skillGrowthToasts';

const mocks = vi.hoisted(() => {
  class FakeApiError extends Error {
    constructor(
      message: string,
      public code: number,
    ) {
      super(message);
    }
  }
  return { ApiError: FakeApiError, updateSkillLifecycle: vi.fn(), rollbackSkillEvolution: vi.fn() };
});

vi.mock('@/lib/api', () => ({ ApiError: mocks.ApiError }));
vi.mock('@/services/skill/core', () => ({ updateSkillLifecycle: mocks.updateSkillLifecycle }));
vi.mock('@/services/skill/growth', () => ({ rollbackSkillEvolution: mocks.rollbackSkillEvolution }));

describe('skill growth toasts', () => {
  const t = (key: string, values?: Record<string, string | number>) => (values ? `${key}:${values.name}` : key);
  const pushToast = { success: vi.fn(), error: vi.fn() };
  const openSkillGrowth = vi.fn();
  const deps = { t, pushToast, openSkillGrowth };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('showSkillLearnedToast', () => {
    it('announces the learned skill once, with view and undo actions', () => {
      showSkillLearnedToast('deploy-flow', deps);

      expect(pushToast.success).toHaveBeenCalledTimes(1);
      expect(pushToast.success).toHaveBeenCalledWith(
        'skillEvolvedNew:deploy-flow',
        expect.objectContaining({
          action: expect.objectContaining({ label: 'openSkillGrowth', onClick: openSkillGrowth }),
          cancel: expect.objectContaining({ label: 'undoEvolve' }),
        }),
      );
    });

    it('archives the skill and confirms when undo is clicked', async () => {
      mocks.updateSkillLifecycle.mockResolvedValue({});
      showSkillLearnedToast('deploy-flow', deps);

      await pushToast.success.mock.calls[0][1].cancel.onClick();

      expect(mocks.updateSkillLifecycle).toHaveBeenCalledWith('deploy-flow', 'archive');
      expect(pushToast.success).toHaveBeenLastCalledWith('skillGrowthUndone:deploy-flow');
      expect(pushToast.error).not.toHaveBeenCalled();
    });

    it('explains the refusal when the skill is pinned or bound', async () => {
      mocks.updateSkillLifecycle.mockRejectedValue(new mocks.ApiError('conflict', 409));
      showSkillLearnedToast('deploy-flow', deps);

      await pushToast.success.mock.calls[0][1].cancel.onClick();

      expect(pushToast.error).toHaveBeenCalledWith('skillGrowthUndoBlocked:deploy-flow');
    });

    it.each([
      ['a missing skill', new mocks.ApiError('missing', 404)],
      ['a network failure', new Error('offline')],
    ])('reports a generic failure for %s', async (_label, error) => {
      mocks.updateSkillLifecycle.mockRejectedValue(error);
      showSkillLearnedToast('deploy-flow', deps);

      await pushToast.success.mock.calls[0][1].cancel.onClick();

      expect(pushToast.error).toHaveBeenCalledWith('skillGrowthUndoFailed:deploy-flow');
    });
  });

  describe('showSkillEvolvedToast', () => {
    const base = { skill_name: 'deploy-flow', evolution_type: 'new', description: 'Ships releases' };

    it('stays silent when the learning was already announced by its growth case', () => {
      showSkillEvolvedToast({ ...base, notify: false }, deps);

      expect(pushToast.success).not.toHaveBeenCalled();
    });

    it.each([
      ['new', 'skillEvolvedNew:deploy-flow'],
      ['patch', 'skillEvolvedPatch:deploy-flow'],
    ])('announces a %s evolution by default', (evolutionType, message) => {
      showSkillEvolvedToast({ ...base, evolution_type: evolutionType }, deps);

      expect(pushToast.success).toHaveBeenCalledWith(
        message,
        expect.objectContaining({ description: 'Ships releases' }),
      );
    });

    it('offers undo only when the evolution can be rolled back', () => {
      showSkillEvolvedToast(base, deps);
      showSkillEvolvedToast({ ...base, evolution_id: 'evo-1' }, deps);

      expect(pushToast.success.mock.calls[0][1].cancel).toBeUndefined();
      expect(pushToast.success.mock.calls[1][1].cancel).toEqual(expect.objectContaining({ label: 'undoEvolve' }));
    });

    it('rolls the evolution back through the authenticated evolution client', async () => {
      mocks.rollbackSkillEvolution.mockResolvedValue(undefined);
      showSkillEvolvedToast({ ...base, evolution_id: 'evo-1' }, deps);

      await pushToast.success.mock.calls[0][1].cancel.onClick();

      expect(mocks.rollbackSkillEvolution).toHaveBeenCalledWith('evo-1');
      expect(pushToast.success).toHaveBeenLastCalledWith('rollbackSuccess:deploy-flow');
    });

    it('reports a failed rollback', async () => {
      mocks.rollbackSkillEvolution.mockRejectedValue(new mocks.ApiError('conflict', 409));
      showSkillEvolvedToast({ ...base, evolution_id: 'evo-1' }, deps);

      await pushToast.success.mock.calls[0][1].cancel.onClick();

      expect(pushToast.error).toHaveBeenCalledWith('rollbackFailed:deploy-flow');
    });
  });
});
