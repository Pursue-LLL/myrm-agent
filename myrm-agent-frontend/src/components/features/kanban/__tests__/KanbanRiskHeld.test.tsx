// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const { sonnerToast, riskToast, agentState } = vi.hoisted(() => ({
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  agentState: { agents: [] as never[], fetchAgents: vi.fn() },
}));

vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
vi.mock('@/store/useAgentStore', () => ({
  default: (select: (state: typeof agentState) => unknown) => select(agentState),
}));

import type { KanbanTask } from '@/services/kanban';
import { useKanbanAddTask } from '../useKanbanAddTask';
import { useKanbanTaskCardDetails } from '../useKanbanTaskCardDetails';
import { useKanbanTaskDrawer } from '../useKanbanTaskDrawer';

const task = { task_id: 'task-1', title: 'Ship it' } as KanbanTask;
const t = (key: string) => key;

function stubFetch(status: number, body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => jsonResponse(status, body)),
  );
}

/** Every hook below must show the one notice for a held text, and its own failure toast for anything else. */
function expectOnlyTheNotice(): void {
  expect(riskToast.error).toHaveBeenCalledTimes(1);
  expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
  expect(sonnerToast.error).not.toHaveBeenCalled();
}

describe('kanban text entry when the server holds the text', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('adding a task', () => {
    const addTask = () => {
      const onCreated = vi.fn(async () => undefined);
      const hook = renderHook(() => useKanbanAddTask({ boardId: 'board-1', onCreated }));
      act(() => hook.result.current.setNewTaskTitle('Deploy with key sk-AAAAAABBBBBBCCCCCCDDDD-0'));
      return { hook, onCreated };
    };

    it('explains a held task once, keeps the typed text and shows no failure toast of its own', async () => {
      stubFetch(400, riskHeldRefusalBody);
      const { hook, onCreated } = addTask();

      await act(() => hook.result.current.handleAddTask());

      expectOnlyTheNotice();
      expect(hook.result.current.newTaskTitle).toBe('Deploy with key sk-AAAAAABBBBBBCCCCCCDDDD-0');
      expect(onCreated).not.toHaveBeenCalled();
    });

    it('still reports any other failure with its own toast', async () => {
      stubFetch(500, { detail: 'boom' });
      const { hook } = addTask();

      await act(() => hook.result.current.handleAddTask());

      expect(sonnerToast.error).toHaveBeenCalledWith('addError');
    });
  });

  describe('commenting on a task card', () => {
    const comment = () => {
      const hook = renderHook(() => useKanbanTaskCardDetails({ task, allTasks: [], onRefresh: vi.fn() }));
      act(() => hook.result.current.setCommentText('use key sk-AAAAAABBBBBBCCCCCCDDDD-0'));
      return hook;
    };

    it('explains a held comment once and keeps it in the box', async () => {
      stubFetch(400, riskHeldRefusalBody);
      const hook = comment();

      await act(() => hook.result.current.handleSubmitComment());

      expectOnlyTheNotice();
      expect(hook.result.current.commentText).toBe('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');
    });

    it('still reports any other failure with its own toast', async () => {
      stubFetch(500, { detail: 'boom' });
      const hook = comment();

      await act(() => hook.result.current.handleSubmitComment());

      expect(sonnerToast.error).toHaveBeenCalledWith('addCommentError');
    });
  });

  describe('the task drawer', () => {
    const drawer = () =>
      renderHook(() =>
        useKanbanTaskDrawer({
          task,
          allTasks: [],
          open: false,
          onOpenChange: vi.fn(),
          onRefresh: vi.fn(),
          onRequestMove: vi.fn(),
          t,
        }),
      );

    it('explains a held comment once and keeps it in the box', async () => {
      stubFetch(400, riskHeldRefusalBody);
      const hook = drawer();
      act(() => hook.result.current.setCommentText('use key sk-AAAAAABBBBBBCCCCCCDDDD-0'));

      await act(() => hook.result.current.handleSubmitComment());

      expectOnlyTheNotice();
      expect(hook.result.current.commentText).toBe('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');
    });

    it('explains held acceptance criteria once and keeps the editor open', async () => {
      stubFetch(400, riskHeldRefusalBody);
      const hook = drawer();
      act(() => {
        hook.result.current.setEditingCriteria(true);
        hook.result.current.setCriteriaText('token sk-AAAAAABBBBBBCCCCCCDDDD-0 works');
      });

      await act(() => hook.result.current.handleSaveCriteria());

      expectOnlyTheNotice();
      expect(hook.result.current.editingCriteria).toBe(true);
    });

    it('explains a held result once and keeps the editor open', async () => {
      stubFetch(400, riskHeldRefusalBody);
      const hook = drawer();
      act(() => {
        hook.result.current.setEditingResult(true);
        hook.result.current.setResultText('deployed with key sk-AAAAAABBBBBBCCCCCCDDDD-0');
      });

      await act(() => hook.result.current.handleSaveResult());

      expectOnlyTheNotice();
      expect(hook.result.current.editingResult).toBe(true);
    });

    it('explains a held rejection reason once and keeps the dialog open with the text', async () => {
      stubFetch(400, riskHeldRefusalBody);
      const hook = drawer();
      act(() => {
        hook.result.current.setShowRejectDialog(true);
        hook.result.current.setRejectReason('retry with key sk-AAAAAABBBBBBCCCCCCDDDD-0');
      });

      await act(() => hook.result.current.handleReject());

      expectOnlyTheNotice();
      expect(hook.result.current.showRejectDialog).toBe(true);
      expect(hook.result.current.rejectReason).toBe('retry with key sk-AAAAAABBBBBBCCCCCCDDDD-0');
    });

    it('still reports any other failure with its own toast', async () => {
      stubFetch(500, { detail: 'boom' });
      const hook = drawer();
      act(() => {
        hook.result.current.setCommentText('write the docs');
        hook.result.current.setResultText('parsed 3 files');
        hook.result.current.setRejectReason('add source citations');
      });

      await act(() => hook.result.current.handleSubmitComment());
      await act(() => hook.result.current.handleSaveCriteria());
      await act(() => hook.result.current.handleSaveResult());
      await act(() => hook.result.current.handleReject());

      expect(sonnerToast.error).toHaveBeenCalledWith('addCommentError');
      expect(sonnerToast.error).toHaveBeenCalledWith('criteriaUpdateError');
      expect(sonnerToast.error).toHaveBeenCalledWith('updateError');
      expect(sonnerToast.error).toHaveBeenCalledWith('rejectError');
    });
  });
});
