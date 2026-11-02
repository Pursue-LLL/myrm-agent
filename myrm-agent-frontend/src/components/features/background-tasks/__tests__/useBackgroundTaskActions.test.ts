// @vitest-environment jsdom
/**
 * What a row's buttons do on a task, apart from how the panel draws them.
 *
 * Real scenario: a media task and a shell task are cancelled from the same panel, and each must refresh its own list;
 * the two refreshers take no argument, so swapping them type-checks and only shows as a list that stays stale.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { toastMock, stableT, cancelTask, cancelMedia, sendStdin, steerTask } = vi.hoisted(() => ({
  stableT: (key: string) => key,
  toastMock: { success: vi.fn(), error: vi.fn() },
  cancelTask: vi.fn(),
  cancelMedia: vi.fn(),
  sendStdin: vi.fn(),
  steerTask: vi.fn(),
}));

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));
vi.mock('@/services/background-tasks', () => ({
  cancelBackgroundTask: cancelTask,
  sendShellBackgroundStdin: sendStdin,
  steerBackgroundTask: steerTask,
}));
vi.mock('@/services/mediaTasks', () => ({ cancelMediaTask: cancelMedia }));
vi.mock('@/services/riskHeldToast', () => ({ isRiskHeldError: () => false }));

import { useBackgroundTaskActions } from '../useBackgroundTaskActions';

const fetchTasks = vi.fn(async () => {});
const refetchMediaTasks = vi.fn(async () => {});

const renderActions = () => renderHook(() => useBackgroundTaskActions({ fetchTasks, refetchMediaTasks }));

describe('useBackgroundTaskActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cancelTask.mockResolvedValue({});
    cancelMedia.mockResolvedValue(undefined);
    sendStdin.mockResolvedValue({});
    steerTask.mockResolvedValue({});
  });

  it('refreshes the task list, not the media list, once a task is cancelled or its leftover stopped', async () => {
    const { result } = renderActions();

    await act(async () => {
      result.current.rowActions.onCancel('shell-1');
      result.current.rowActions.onStopLeftover('shell-2');
    });

    await waitFor(() => expect(fetchTasks).toHaveBeenCalledTimes(2));
    expect(cancelTask.mock.calls).toEqual([['shell-1'], ['shell-2']]);
    expect(toastMock.success.mock.calls).toEqual([['cancelSuccess'], ['leftoverStopSuccess']]);
    expect(refetchMediaTasks).not.toHaveBeenCalled();
  });

  it('says the program could not be stopped, and still refreshes, when the server finds it alive after the stop', async () => {
    cancelTask.mockResolvedValueOnce({ message: 'cancelled', task_id: 'shell-1', leftover_processes: 2 });
    const { result } = renderActions();

    await act(async () => {
      result.current.rowActions.onStopLeftover('shell-1');
    });

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('leftoverStopFailed'));
    expect(toastMock.success).not.toHaveBeenCalled();
    expect(fetchTasks).toHaveBeenCalledTimes(1);
  });

  it('confirms a cancel as a cancel even when the program survives, which the refreshed row then shows', async () => {
    cancelTask.mockResolvedValueOnce({ message: 'cancelled', task_id: 'shell-1', leftover_processes: 2 });
    const { result } = renderActions();

    await act(async () => {
      result.current.rowActions.onCancel('shell-1');
    });

    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('cancelSuccess'));
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(fetchTasks).toHaveBeenCalledTimes(1);
  });

  it('refreshes the media list, not the task list, once a media task is cancelled', async () => {
    const { result } = renderActions();

    await act(async () => {
      await result.current.handleCancelMediaTask('media-1');
    });

    expect(cancelMedia).toHaveBeenCalledWith('media-1');
    expect(toastMock.success).toHaveBeenCalledWith('cancelSuccess');
    expect(refetchMediaTasks).toHaveBeenCalledTimes(1);
    expect(fetchTasks).not.toHaveBeenCalled();
  });

  it('says so and leaves the list alone when the server refuses a cancel', async () => {
    cancelTask.mockRejectedValueOnce(new Error('network down'));
    const { result } = renderActions();

    await act(async () => {
      result.current.rowActions.onCancel('shell-1');
    });

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('cancelFailed'));
    expect(fetchTasks).not.toHaveBeenCalled();
  });

  it('sends the steer text trimmed, then closes and empties the steer input without a list refresh', async () => {
    const { result } = renderActions();
    act(() => result.current.rowActions.onToggleSteer('agent-1'));
    act(() => result.current.rowActions.onSteerInputChange('  focus on EU prices  '));

    await act(async () => {
      result.current.rowActions.onSteer('agent-1');
    });

    await waitFor(() => expect(result.current.rowActions).toMatchObject({ steerTaskId: null, steerInput: '' }));
    expect(steerTask).toHaveBeenCalledWith('agent-1', 'focus on EU prices');
    expect(toastMock.success).toHaveBeenCalledWith('steerSuccess');
    expect(sendStdin).not.toHaveBeenCalled();
    expect(fetchTasks).not.toHaveBeenCalled();
  });

  it('sends the typed stdin text as a submission, then closes and empties the stdin input and refreshes', async () => {
    const { result } = renderActions();
    act(() => result.current.rowActions.onToggleShellInput('shell-1'));
    act(() => result.current.rowActions.onShellInputChange('y'));

    await act(async () => {
      result.current.rowActions.onShellInputSend('shell-1');
    });

    await waitFor(() => expect(result.current.rowActions).toMatchObject({ shellInputTaskId: null, shellInput: '' }));
    expect(sendStdin).toHaveBeenCalledWith('shell-1', 'y', { submit: true });
    expect(toastMock.success).toHaveBeenCalledWith('shellInputSuccess');
    expect(steerTask).not.toHaveBeenCalled();
    expect(fetchTasks).toHaveBeenCalledTimes(1);
  });

  it('closes and empties the stdin input, then refreshes, once the shell took the close', async () => {
    const { result } = renderActions();
    act(() => result.current.rowActions.onToggleShellInput('shell-1'));
    act(() => result.current.rowActions.onShellInputChange('yes'));
    expect(result.current.rowActions).toMatchObject({ shellInputTaskId: 'shell-1', shellInput: 'yes' });

    await act(async () => {
      result.current.rowActions.onShellInputClose('shell-1');
    });

    await waitFor(() => expect(result.current.rowActions).toMatchObject({ shellInputTaskId: null, shellInput: '' }));
    expect(sendStdin).toHaveBeenCalledWith('shell-1', '', { close: true });
    expect(toastMock.success).toHaveBeenCalledWith('shellInputCloseSuccess');
    expect(fetchTasks).toHaveBeenCalledTimes(1);
  });

  it('keeps the stdin input as typed when the close fails', async () => {
    sendStdin.mockRejectedValueOnce(new Error('network down'));
    const { result } = renderActions();
    act(() => result.current.rowActions.onToggleShellInput('shell-1'));
    act(() => result.current.rowActions.onShellInputChange('yes'));

    await act(async () => {
      result.current.rowActions.onShellInputClose('shell-1');
    });

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('shellInputCloseFailed'));
    expect(result.current.rowActions).toMatchObject({ shellInputTaskId: 'shell-1', shellInput: 'yes' });
    expect(fetchTasks).not.toHaveBeenCalled();
  });

  it('opens the steer and the stdin input one at a time, and a second press on the same one closes it', () => {
    const { result } = renderActions();
    act(() => result.current.rowActions.onToggleSteer('agent-1'));
    act(() => result.current.rowActions.onSteerInputChange('focus on EU prices'));
    expect(result.current.rowActions).toMatchObject({ steerTaskId: 'agent-1', steerInput: 'focus on EU prices' });

    act(() => result.current.rowActions.onToggleShellInput('shell-1'));
    expect(result.current.rowActions).toMatchObject({
      steerTaskId: null,
      steerInput: '',
      shellInputTaskId: 'shell-1',
    });

    act(() => result.current.rowActions.onToggleShellInput('shell-1'));
    expect(result.current.rowActions.shellInputTaskId).toBeNull();
  });
});
