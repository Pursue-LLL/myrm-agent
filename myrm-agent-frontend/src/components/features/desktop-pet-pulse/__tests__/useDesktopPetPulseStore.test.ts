import { beforeEach, describe, expect, it } from 'vitest';
import { useDesktopPetPulseStore } from '../useDesktopPetPulseStore';
import type { PetApprovalNotice } from '../desktopPetPulseTypes';

describe('useDesktopPetPulseStore', () => {
  beforeEach(() => {
    useDesktopPetPulseStore.getState().resetAll();
  });

  it('初始状态合规且支持重置', () => {
    const state = useDesktopPetPulseStore.getState();
    expect(state.petStatus).toBe('idle');
    expect(state.isPaused).toBe(false);
    expect(state.activeApproval).toBeNull();
    expect(state.isVoiceInputActive).toBe(false);
    expect(state.isMigrationModalOpen).toBe(false);
  });

  it('支持修改桌宠状态与暂停切换', () => {
    const store = useDesktopPetPulseStore.getState();
    store.setPetStatus('working');
    expect(useDesktopPetPulseStore.getState().petStatus).toBe('working');

    store.togglePause();
    expect(useDesktopPetPulseStore.getState().isPaused).toBe(true);

    store.togglePause();
    expect(useDesktopPetPulseStore.getState().isPaused).toBe(false);
  });

  it('设置待审批时自动将桌宠状态切换为 approval_needed', () => {
    const notice: PetApprovalNotice = {
      id: 'appr-1',
      title: '高危脚本执行确认',
      description: '即将执行 rm 指令',
      toolName: 'run_bash',
      agentId: 'ag-1',
      agentName: '自动化运维',
    };

    useDesktopPetPulseStore.getState().setActiveApproval(notice);
    const state = useDesktopPetPulseStore.getState();
    expect(state.activeApproval).toEqual(notice);
    expect(state.petStatus).toBe('approval_needed');

    useDesktopPetPulseStore.getState().setActiveApproval(null);
    expect(useDesktopPetPulseStore.getState().activeApproval).toBeNull();
  });

  it('支持智能体入队与出队管理', () => {
    const store = useDesktopPetPulseStore.getState();
    store.enqueueAgent('ag-sub-1', 'queued');
    store.enqueueAgent('ag-sub-2', 'approving');

    expect(useDesktopPetPulseStore.getState().activeQueue.length).toBe(2);

    store.dequeueAgent('ag-sub-1');
    const queue = useDesktopPetPulseStore.getState().activeQueue;
    expect(queue.length).toBe(1);
    expect(queue[0].agentId).toBe('ag-sub-2');
  });

  it('支持语音直通任务派发并自动联动桌宠状态', () => {
    const payload = useDesktopPetPulseStore
      .getState()
      .triggerDirectVoiceDispatch('请生成本周代码审查统计', true);

    expect(payload.prompt).toBe('请生成本周代码审查统计');
    expect(payload.autoRun).toBe(true);

    const state = useDesktopPetPulseStore.getState();
    expect(state.petStatus).toBe('thinking');
    expect(state.isVoiceInputActive).toBe(false);
    expect(state.voiceState.isRecording).toBe(false);
  });

  it('双击唤出主工作台会自增 mainWindowFocusedCount', () => {
    const initialCount =
      useDesktopPetPulseStore.getState().mainWindowFocusedCount;
    useDesktopPetPulseStore.getState().requestOpenMainWindow();
    expect(
      useDesktopPetPulseStore.getState().mainWindowFocusedCount
    ).toBe(initialCount + 1);
  });
});
