import { describe, expect, it, vi } from 'vitest';

import { showMemoryOperationToasts } from '@/hooks/globalEvents/memoryOperationToasts';

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: toastMocks,
}));

describe('showMemoryOperationToasts', () => {
  const router = { push: vi.fn() };
  const t = (key: string, values?: Record<string, string | number>) =>
    values ? `${key}:${JSON.stringify(values)}` : key;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows success toast for auto-approved goal completion', () => {
    showMemoryOperationToasts(
      {
        operation: 'goal_completion_consolidation',
        auto_approved: true,
        decision_count: 2,
        context_name: 'Team Memory',
      },
      { t, router },
    );

    expect(toastMocks.success).toHaveBeenCalledOnce();
    expect(toastMocks.info).not.toHaveBeenCalled();
  });

  it('shows pending toast with review action for goal completion', () => {
    showMemoryOperationToasts(
      {
        operation: 'goal_completion_consolidation',
        auto_approved: false,
        decision_count: 1,
        context_name: 'Team Memory',
      },
      { t, router },
    );

    expect(toastMocks.info).toHaveBeenCalledOnce();
    const call = toastMocks.info.mock.calls[0];
    expect(call[1]?.action?.label).toBe('reviewSharedContextProposal');
    call[1]?.action?.onClick();
    expect(router.push).toHaveBeenCalledWith('/settings/memory?tab=shared');
  });

  it('shows success toast for auto-approved correction propagation', () => {
    showMemoryOperationToasts(
      {
        operation: 'correction_propagation',
        auto_approved: true,
        context_name: 'Team Memory',
      },
      { t, router },
    );

    expect(toastMocks.success).toHaveBeenCalledWith(
      'correctionMemorySynced',
      expect.objectContaining({ description: 'Team Memory' }),
    );
  });

  it('shows pending toast with review action for correction propagation', () => {
    showMemoryOperationToasts(
      {
        operation: 'correction_propagation',
        auto_approved: false,
        context_name: 'Team Memory',
      },
      { t, router },
    );

    expect(toastMocks.info).toHaveBeenCalledOnce();
    const call = toastMocks.info.mock.calls[0];
    call[1]?.action?.onClick();
    expect(router.push).toHaveBeenCalledWith('/settings/memory?tab=shared');
  });

  it('shows error toast for goal completion failure', () => {
    showMemoryOperationToasts({ operation: 'goal_completion_consolidation_failed' }, { t, router });

    expect(toastMocks.error).toHaveBeenCalledWith(
      'goalMemoryArchiveFailed',
      expect.objectContaining({ duration: 10_000 }),
    );
  });

  it('shows success toast for frustration skill learned', () => {
    showMemoryOperationToasts(
      {
        operation: 'frustration_skill_learned',
        skill_name: 'python-development',
        preference: 'Never add comments unless explaining non-obvious logic',
      },
      { t, router },
    );

    expect(toastMocks.success).toHaveBeenCalledOnce();
    const call = toastMocks.success.mock.calls[0];
    expect(call[0]).toContain('frustrationSkillLearned');
    expect(call[1]?.description).toBe('Never add comments unless explaining non-obvious logic');
  });

  it('does nothing for unknown operation', () => {
    showMemoryOperationToasts({ operation: 'unknown_operation' }, { t, router });

    expect(toastMocks.success).not.toHaveBeenCalled();
    expect(toastMocks.info).not.toHaveBeenCalled();
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  describe('auto_memory_extracted with throttle', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('throttles and merges multiple extract events into one toast', () => {
      showMemoryOperationToasts({ operation: 'auto_memory_extracted', count: 3 }, { t, router });
      showMemoryOperationToasts({ operation: 'auto_memory_extracted', count: 2 }, { t, router });

      expect(toastMocks.success).not.toHaveBeenCalled();

      vi.advanceTimersByTime(2_000);

      expect(toastMocks.success).toHaveBeenCalledOnce();
      const call = toastMocks.success.mock.calls[0];
      expect(call[0]).toContain('autoMemoryExtracted');
      expect(call[0]).toContain('5');
      expect(call[1]?.action?.label).toBe('viewMemoryCenter');
    });

    it('defaults count to 1 when not provided', () => {
      showMemoryOperationToasts({ operation: 'auto_memory_extracted' }, { t, router });
      vi.advanceTimersByTime(2_000);

      expect(toastMocks.success).toHaveBeenCalledOnce();
      const call = toastMocks.success.mock.calls[0];
      expect(call[0]).toContain('1');
    });

    it('navigates to memory center on action click', () => {
      showMemoryOperationToasts({ operation: 'auto_memory_extracted', count: 1 }, { t, router });
      vi.advanceTimersByTime(2_000);

      toastMocks.success.mock.calls[0][1]?.action?.onClick();
      expect(router.push).toHaveBeenCalledWith('/settings/memory');
    });
  });

  describe('operation_ledger kind fallback', () => {
    it('shows info toast for write kind', () => {
      showMemoryOperationToasts(
        { kind: 'write', description: 'User prefers dark theme', status: 'success' },
        { t, router },
      );

      expect(toastMocks.info).toHaveBeenCalledOnce();
      const call = toastMocks.info.mock.calls[0];
      expect(call[0]).toBe('memoryRecallUpdated');
      expect(call[1]?.description).toBe('User prefers dark theme');
    });

    it('shows info toast for forget kind', () => {
      showMemoryOperationToasts(
        { kind: 'forget', description: 'Removed outdated preference', status: 'success' },
        { t, router },
      );

      expect(toastMocks.info).toHaveBeenCalledOnce();
    });

    it('skips toast when status is skipped', () => {
      showMemoryOperationToasts(
        { kind: 'write', description: 'test', status: 'skipped' },
        { t, router },
      );

      expect(toastMocks.info).not.toHaveBeenCalled();
    });

    it('skips toast when status is error', () => {
      showMemoryOperationToasts(
        { kind: 'write', description: 'test', status: 'error' },
        { t, router },
      );

      expect(toastMocks.info).not.toHaveBeenCalled();
    });

    it('skips toast for unhandled kind', () => {
      showMemoryOperationToasts(
        { kind: 'recall', description: 'test', status: 'success' },
        { t, router },
      );

      expect(toastMocks.info).not.toHaveBeenCalled();
    });

    it('navigates to memory center on action click', () => {
      showMemoryOperationToasts(
        { kind: 'write', description: 'test', status: 'success' },
        { t, router },
      );

      toastMocks.info.mock.calls[0][1]?.action?.onClick();
      expect(router.push).toHaveBeenCalledWith('/settings/memory');
    });
  });
});
