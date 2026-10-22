import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useInFlightSteerStore } from '../useInFlightSteerStore';
import { cancelBackgroundTask, steerBackgroundTask } from '@/services/background-tasks';
import { showI18nToast } from '@/services/i18nToastService';
import { toast } from '@/lib/utils/toast';

vi.mock('@/services/background-tasks', () => ({
  steerBackgroundTask: vi.fn().mockResolvedValue({ message: 'steered', task_id: 'task-1' }),
  cancelBackgroundTask: vi.fn().mockResolvedValue({ message: 'cancelled', task_id: 'task-1' }),
}));

vi.mock('@/services/i18nToastService', () => ({ showI18nToast: vi.fn() }));
vi.mock('@/lib/utils/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('useInFlightSteerStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useInFlightSteerStore.getState().clearSwimlanes();
  });

  it('registers new subagent swimlanes and merges existing updates', () => {
    const store = useInFlightSteerStore.getState();
    store.registerSwimlane({
      id: 'sub-1',
      name: 'Code Reviewer',
      role: 'Reviewer',
      status: 'running',
      currentStep: 'AST Analysis',
      tokensUsed: 1200,
      elapsedSeconds: 15,
      taskId: 'task-1',
    });

    let state = useInFlightSteerStore.getState();
    expect(state.swimlanes).toHaveLength(1);
    expect(state.swimlanes[0].name).toBe('Code Reviewer');
    expect(state.swimlanes[0].tokensUsed).toBe(1200);

    // Merge update with same ID
    store.registerSwimlane({
      id: 'sub-1',
      name: 'Code Reviewer',
      role: 'Reviewer',
      status: 'running',
      currentStep: 'Linting check',
      tokensUsed: 2500,
      elapsedSeconds: 28,
    });

    state = useInFlightSteerStore.getState();
    expect(state.swimlanes).toHaveLength(1);
    expect(state.swimlanes[0].currentStep).toBe('Linting check');
    expect(state.swimlanes[0].tokensUsed).toBe(2500);
  });

  it('updates swimlane status, step, and tokens', () => {
    const store = useInFlightSteerStore.getState();
    store.registerSwimlane({
      id: 'sub-2',
      name: 'Tester Bot',
      role: 'QA',
      status: 'running',
      currentStep: 'Running Vitest',
      tokensUsed: 800,
      elapsedSeconds: 10,
    });

    store.updateSwimlaneStatus('sub-2', 'paused', 'Awaiting approval', 1500);
    const updated = useInFlightSteerStore.getState().swimlanes[0];
    expect(updated.status).toBe('paused');
    expect(updated.currentStep).toBe('Awaiting approval');
    expect(updated.tokensUsed).toBe(1500);
  });

  it('removes swimlane and resets active popover if open', () => {
    const store = useInFlightSteerStore.getState();
    store.registerSwimlane({
      id: 'sub-3',
      name: 'DB Migrator',
      role: 'DBA',
      status: 'running',
      currentStep: 'Schema migration',
      tokensUsed: 500,
      elapsedSeconds: 8,
    });

    store.openSteerPopover('sub-3');
    expect(useInFlightSteerStore.getState().activePopoverSubagentId).toBe('sub-3');

    store.removeSwimlane('sub-3');
    expect(useInFlightSteerStore.getState().swimlanes).toHaveLength(0);
    expect(useInFlightSteerStore.getState().activePopoverSubagentId).toBeNull();
  });

  it('sends steer instruction, calls background-tasks service and updates state', async () => {
    const store = useInFlightSteerStore.getState();
    store.registerSwimlane({
      id: 'sub-4',
      name: 'Searcher',
      role: 'Researcher',
      status: 'running',
      currentStep: 'Querying external docs',
      tokensUsed: 3000,
      elapsedSeconds: 40,
      taskId: 'task-search-99',
    });

    const success = await store.sendSteerInstruction('sub-4', 'Focus on official 2026 docs only');

    expect(success).toBe(true);
    expect(steerBackgroundTask).toHaveBeenCalledWith('task-search-99', 'Focus on official 2026 docs only');

    const sub = useInFlightSteerStore.getState().swimlanes[0];
    expect(sub.lastInstruction).toBe('Focus on official 2026 docs only');
    expect(sub.lastSteeredAt).toBeDefined();
    expect(sub.currentStep).toContain('已注入纠偏');
  });

  it('handles empty steer instruction safely', async () => {
    const store = useInFlightSteerStore.getState();
    store.registerSwimlane({
      id: 'sub-5',
      name: 'Worker',
      role: 'Worker',
      status: 'running',
      currentStep: 'Idle',
      tokensUsed: 0,
      elapsedSeconds: 0,
    });

    const result = await store.sendSteerInstruction('sub-5', '   ');
    expect(result).toBe(false);
    expect(steerBackgroundTask).not.toHaveBeenCalled();
  });

  it('stops subagent gracefully and preserves partial deliverable artifact', async () => {
    const store = useInFlightSteerStore.getState();
    store.registerSwimlane({
      id: 'sub-6',
      name: 'Architect',
      role: 'Lead',
      status: 'running',
      currentStep: 'Writing system spec',
      tokensUsed: 4500,
      elapsedSeconds: 65,
      taskId: 'task-arch-1',
    });

    const success = await store.stopAndKeepArtifacts('sub-6');
    expect(success).toBe(true);
    expect(cancelBackgroundTask).toHaveBeenCalledWith('task-arch-1');

    const sub = useInFlightSteerStore.getState().swimlanes[0];
    expect(sub.status).toBe('stopped');
    expect(sub.currentStep).toContain('已提前叫停 (保留半成品草稿)');
    expect(sub.partialDeliverable).toBeDefined();
    expect(sub.partialDeliverable?.title).toBe('Architect 半成品产物');
  });

  it('manages task summaries and collapse toggle', () => {
    const store = useInFlightSteerStore.getState();
    store.setTaskSummary({
      id: 'summary-1',
      chatId: 'chat-42',
      goalTitle: 'Multi-Agent Refactor',
      totalSteps: 5,
      completedSteps: 3,
      currentActiveAgentName: 'Test Engineer',
      keyFindings: ['Completed AST parser', 'Generated 15 tests'],
      isCollapsed: true,
      updatedAt: Date.now(),
    });

    expect(useInFlightSteerStore.getState().taskSummaries['summary-1']).toBeDefined();
    expect(useInFlightSteerStore.getState().taskSummaries['summary-1'].isCollapsed).toBe(true);

    store.toggleSummaryCollapse('summary-1');
    expect(useInFlightSteerStore.getState().taskSummaries['summary-1'].isCollapsed).toBe(false);

    store.toggleSummaryCollapse('summary-1');
    expect(useInFlightSteerStore.getState().taskSummaries['summary-1'].isCollapsed).toBe(true);
  });

  describe('user-facing toasts', () => {
    const lane = {
      id: 'sub-t',
      name: 'Toast Lane',
      role: 'Worker',
      status: 'running' as const,
      currentStep: 'Working',
      tokensUsed: 0,
      elapsedSeconds: 0,
      taskId: 'task-toast',
    };

    it('reports an unknown target through the translated toast, for steer and for stop', async () => {
      const store = useInFlightSteerStore.getState();

      expect(await store.sendSteerInstruction('ghost', 'go left')).toBe(false);
      expect(await store.stopAndKeepArtifacts('ghost')).toBe(false);

      expect(showI18nToast).toHaveBeenCalledTimes(2);
      expect(showI18nToast).toHaveBeenNthCalledWith(1, 'chat.inFlightSteer.subagentNotFound', undefined, {
        type: 'error',
      });
      expect(showI18nToast).toHaveBeenNthCalledWith(2, 'chat.inFlightSteer.subagentNotFound', undefined, {
        type: 'error',
      });
    });

    it('confirms a steer and a stop with the sub-agent name', async () => {
      const store = useInFlightSteerStore.getState();
      store.registerSwimlane(lane);

      await store.sendSteerInstruction('sub-t', 'narrow the scope');
      expect(showI18nToast).toHaveBeenLastCalledWith(
        'chat.inFlightSteer.steerSent',
        { name: 'Toast Lane' },
        { type: 'success' },
      );

      await store.stopAndKeepArtifacts('sub-t');
      expect(showI18nToast).toHaveBeenLastCalledWith(
        'chat.inFlightSteer.stopped',
        { name: 'Toast Lane' },
        { type: 'success' },
      );
    });

    it.each([
      ['steer', steerBackgroundTask, 'chat.inFlightSteer.steerFailed'],
      ['stop', cancelBackgroundTask, 'chat.inFlightSteer.stopFailed'],
    ] as const)(
      'on a failed %s shows the server reason, else the translated fallback',
      async (action, service, key) => {
        const store = useInFlightSteerStore.getState();
        store.registerSwimlane(lane);
        const run = () =>
          action === 'steer' ? store.sendSteerInstruction('sub-t', 'narrow') : store.stopAndKeepArtifacts('sub-t');
        const failing = vi.mocked(service);

        failing.mockRejectedValueOnce(new Error('upstream said no'));
        expect(await run()).toBe(false);
        expect(toast.error).toHaveBeenLastCalledWith('upstream said no');
        expect(showI18nToast).not.toHaveBeenCalled();

        failing.mockRejectedValueOnce(new Error(''));
        expect(await run()).toBe(false);
        expect(showI18nToast).toHaveBeenLastCalledWith(key, undefined, { type: 'error' });

        failing.mockRejectedValueOnce('not an Error instance');
        expect(await run()).toBe(false);
        expect(showI18nToast).toHaveBeenLastCalledWith(key, undefined, { type: 'error' });
        expect(showI18nToast).toHaveBeenCalledTimes(2);
      },
    );
  });
});
