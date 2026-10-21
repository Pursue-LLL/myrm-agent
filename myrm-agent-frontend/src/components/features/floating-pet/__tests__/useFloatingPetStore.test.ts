import { describe, it, expect, beforeEach } from 'vitest';
import { useFloatingPetStore } from '../useFloatingPetStore';

describe('useFloatingPetStore', () => {
  beforeEach(() => {
    useFloatingPetStore.getState().reset();
  });

  it('初始状态规范合规', () => {
    const state = useFloatingPetStore.getState();
    expect(state.mood).toBe('idle');
    expect(state.position).toBe('right_edge');
    expect(state.isPinned).toBe(false);
    expect(state.isVoiceRecording).toBe(false);
    expect(state.activeTask).toBeNull();
    expect(state.recentTasks).toEqual([]);
    expect(state.isBubbleExpanded).toBe(false);
  });

  it('按住说话开始与松开发射后台任务流转', () => {
    const store = useFloatingPetStore.getState();
    store.startPushToTalk();

    expect(useFloatingPetStore.getState().isVoiceRecording).toBe(true);
    expect(useFloatingPetStore.getState().mood).toBe('listening');

    const createdTask = store.stopPushToTalk(
      '帮做一个书画作品定制的报价工具，自动计算价格'
    );
    expect(createdTask).not.toBeNull();
    expect(createdTask?.title).toContain('书画作品定制');

    const stateAfter = useFloatingPetStore.getState();
    expect(stateAfter.isVoiceRecording).toBe(false);
    expect(stateAfter.mood).toBe('thinking');
    expect(stateAfter.isBubbleExpanded).toBe(true);
    expect(stateAfter.activeTask?.id).toBe(createdTask?.id);
  });

  it('更新后台任务进度并自动流转情绪状态', () => {
    const store = useFloatingPetStore.getState();
    const task = store.stopPushToTalk('测试任务');
    expect(task).toBeDefined();

    if (task) {
      // 推进进度到 50%
      store.updateTaskProgress(task.id, 50, 'running');
      expect(useFloatingPetStore.getState().activeTask?.progress).toBe(50);
      expect(useFloatingPetStore.getState().mood).toBe('working');

      // 完成任务到 100%
      store.updateTaskProgress(task.id, 100, 'completed');
      expect(useFloatingPetStore.getState().activeTask?.progress).toBe(100);
      expect(useFloatingPetStore.getState().mood).toBe('celebrating');
      expect(useFloatingPetStore.getState().recentTasks.length).toBe(1);
    }
  });

  it('支持展开折叠气泡与切换贴边吸附位置', () => {
    const store = useFloatingPetStore.getState();
    store.toggleBubbleExpanded(true);
    expect(useFloatingPetStore.getState().isBubbleExpanded).toBe(true);

    store.setDockPosition('bottom_right');
    expect(useFloatingPetStore.getState().position).toBe('bottom_right');

    store.setPinned(true);
    expect(useFloatingPetStore.getState().isPinned).toBe(true);
  });

  it('清空当前任务并归档', () => {
    const store = useFloatingPetStore.getState();
    store.stopPushToTalk('临时任务');
    expect(useFloatingPetStore.getState().activeTask).not.toBeNull();

    store.clearActiveTask();
    expect(useFloatingPetStore.getState().activeTask).toBeNull();
    expect(useFloatingPetStore.getState().mood).toBe('idle');
    expect(useFloatingPetStore.getState().isBubbleExpanded).toBe(false);
    expect(useFloatingPetStore.getState().recentTasks.length).toBe(1);
  });
});
