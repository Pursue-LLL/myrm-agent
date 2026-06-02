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
});
