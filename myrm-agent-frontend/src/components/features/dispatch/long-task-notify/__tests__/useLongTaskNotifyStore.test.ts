import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useLongTaskNotifyStore } from '../useLongTaskNotifyStore';

describe('useLongTaskNotifyStore Zustand store', () => {
  beforeEach(() => {
    useLongTaskNotifyStore.getState().resetState();
  });

  it('initializes with default active task and modal states', () => {
    const state = useLongTaskNotifyStore.getState();
    expect(state.activeTask?.taskId).toBe('task-long-9821');
    expect(state.activeTask?.status).toBe('running_unattended');
    expect(state.isDispatchModalOpen).toBe(false);
    expect(state.isReviewModalOpen).toBe(false);
    expect(state.isBackgrounded).toBe(false);
  });

  it('manages modal visibility for dispatch and review modals', () => {
    useLongTaskNotifyStore.getState().openDispatchModal();
    expect(useLongTaskNotifyStore.getState().isDispatchModalOpen).toBe(true);

    useLongTaskNotifyStore.getState().closeDispatchModal();
    expect(useLongTaskNotifyStore.getState().isDispatchModalOpen).toBe(false);

    useLongTaskNotifyStore.getState().openReviewModal();
    expect(useLongTaskNotifyStore.getState().isReviewModalOpen).toBe(true);

    useLongTaskNotifyStore.getState().closeReviewModal();
    expect(useLongTaskNotifyStore.getState().isReviewModalOpen).toBe(false);
  });

  it('dispatches fire-and-forget task and emits custom window event', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const newTask = useLongTaskNotifyStore.getState().dispatchTask({
      title: '地铁碎片时间压测',
      prompt: '跑通完整基准测试',
      estimatedDurationSec: 300,
      notifyWebPush: true,
      notifySystem: false,
    });

    expect(newTask.title).toBe('地铁碎片时间压测');
    expect(newTask.executionEnv).toBe('cloud-server');
    expect(newTask.notifyChannels).toEqual(['web-push']);
    expect(useLongTaskNotifyStore.getState().activeTask?.taskId).toBe(newTask.taskId);
    expect(useLongTaskNotifyStore.getState().isDispatchModalOpen).toBe(false);

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'myrm:long-task-dispatched',
      })
    );

    dispatchSpy.mockRestore();
  });

  it('updates task step and progress percentage via simulateStepProgress', () => {
    useLongTaskNotifyStore
      .getState()
      .simulateStepProgress('执行第4步：汇总生成最终结构化数据', 85);

    const task = useLongTaskNotifyStore.getState().activeTask;
    expect(task?.currentStep).toBe('执行第4步：汇总生成最终结构化数据');
    expect(task?.progressPercent).toBe(85);
  });

  it('tracks background mode and emits rejoin event on rejoinActiveTask', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useLongTaskNotifyStore.getState().toggleBackgroundMode(true);
    expect(useLongTaskNotifyStore.getState().isBackgrounded).toBe(true);

    useLongTaskNotifyStore.getState().rejoinActiveTask();
    expect(useLongTaskNotifyStore.getState().isBackgrounded).toBe(false);

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'myrm:long-task-rejoined',
      })
    );

    dispatchSpy.mockRestore();
  });

  it('completes task, populates checklist, opens review modal and emits completion event', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useLongTaskNotifyStore.getState().completeTask();
    const state = useLongTaskNotifyStore.getState();

    expect(state.activeTask?.status).toBe('completed');
    expect(state.activeTask?.progressPercent).toBe(100);
    expect(state.activeTask?.pushSent).toBe(true);
    expect(state.isReviewModalOpen).toBe(true);
    expect(state.taskHistory.length).toBe(1);

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'myrm:long-task-completed',
      })
    );

    dispatchSpy.mockRestore();
  });
});
