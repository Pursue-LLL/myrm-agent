import { describe, it, expect, beforeEach } from 'vitest';
import { usePetSpeechLoopStore } from '../usePetSpeechLoopStore';

describe('usePetSpeechLoopStore', () => {
  beforeEach(() => {
    usePetSpeechLoopStore.getState().reset();
  });

  it('初始状态处于待命、平静、麦克风关闭状态', () => {
    const state = usePetSpeechLoopStore.getState();
    expect(state.currentPhase).toBe('idle');
    expect(state.voiceStatus).toBe('inactive');
    expect(state.petMood).toBe('calm');
    expect(state.steps).toEqual([]);
    expect(state.approvalAction).toBeNull();
    expect(state.isApprovalDrawerOpen).toBe(false);
    expect(state.isWiggling).toBe(false);
  });

  it('能够开启和停止麦克风语音监听并同步更新桌宠气泡', () => {
    const store = usePetSpeechLoopStore.getState();
    store.startVoiceCapture();

    const listeningState = usePetSpeechLoopStore.getState();
    expect(listeningState.voiceStatus).toBe('listening');
    expect(listeningState.currentPhase).toBe('listening');
    expect(listeningState.petMood).toBe('listening');
    expect(listeningState.bubbleMessage).toContain('我在听');

    store.stopVoiceCapture();
    expect(usePetSpeechLoopStore.getState().voiceStatus).toBe('inactive');
  });

  it('流式语音输入阶段：中间结果实时回显，最终结果自动触发四阶流水线', () => {
    const store = usePetSpeechLoopStore.getState();

    // 1. 中间临时语音片段
    store.feedVoiceInput('帮我做一个', false);
    expect(usePetSpeechLoopStore.getState().interimTranscript).toBe(
      '帮我做一个'
    );
    expect(usePetSpeechLoopStore.getState().bubbleMessage).toContain(
      '帮我做一个'
    );

    // 2. 最终判定静音截断并确认完整指令
    store.feedVoiceInput('帮我做一个微型统计看板', true);
    const triggered = usePetSpeechLoopStore.getState();
    expect(triggered.transcript).toBe('帮我做一个微型统计看板');
    expect(triggered.interimTranscript).toBe('');
    expect(triggered.currentPhase).toBe('planning');
    expect(triggered.petMood).toBe('thinking');
    expect(triggered.steps).toHaveLength(4);
    expect(triggered.approvalAction).not.toBeNull();
    expect(triggered.steps[0].status).toBe('running');
  });

  it('能够顺序推进 Plan -> Code -> Exec -> Reviewing -> Completed 阶段', () => {
    const store = usePetSpeechLoopStore.getState();
    store.triggerSpeechPromptLoop('生成新功能模块');

    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('planning');

    // 推进至 coding
    store.advanceToNextPhase();
    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('coding');
    expect(usePetSpeechLoopStore.getState().petMood).toBe('coding');

    // 推进至 executing
    store.advanceToNextPhase();
    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('executing');

    // 推进至 reviewing
    store.advanceToNextPhase();
    const reviewingState = usePetSpeechLoopStore.getState();
    expect(reviewingState.currentPhase).toBe('reviewing');
    expect(reviewingState.isApprovalDrawerOpen).toBe(true);
    expect(reviewingState.petMood).toBe('alert');

    // 推进至 completed
    store.advanceToNextPhase();
    const completedState = usePetSpeechLoopStore.getState();
    expect(completedState.currentPhase).toBe('completed');
    expect(completedState.isApprovalDrawerOpen).toBe(false);
    expect(completedState.isWiggling).toBe(true);
    expect(completedState.petMood).toBe('celebrating');

    // 再次推进回到 idle
    store.advanceToNextPhase();
    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('idle');
  });

  it('支持一键拍板批准，完成交付并触发庆祝动画', () => {
    const store = usePetSpeechLoopStore.getState();
    store.runFullCycle('快速修复样式');

    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('reviewing');
    expect(usePetSpeechLoopStore.getState().isApprovalDrawerOpen).toBe(true);

    store.approveAction();

    const afterApprove = usePetSpeechLoopStore.getState();
    expect(afterApprove.approvalAction?.status).toBe('approved');
    expect(afterApprove.isApprovalDrawerOpen).toBe(false);
    expect(afterApprove.currentPhase).toBe('completed');
    expect(afterApprove.isWiggling).toBe(true);
  });

  it('支持修改撤回，取消当前方案并安全回退到待命', () => {
    const store = usePetSpeechLoopStore.getState();
    store.runFullCycle('测试危险指令');

    store.rejectAction();

    const afterReject = usePetSpeechLoopStore.getState();
    expect(afterReject.approvalAction?.status).toBe('rejected');
    expect(afterReject.isApprovalDrawerOpen).toBe(false);
    expect(afterReject.currentPhase).toBe('idle');
  });

  it('调用 reset 能够彻底还原所有状态与流水线', () => {
    const store = usePetSpeechLoopStore.getState();
    store.runFullCycle('测试重置');
    expect(usePetSpeechLoopStore.getState().steps.length).toBeGreaterThan(0);

    store.reset();
    const resetState = usePetSpeechLoopStore.getState();
    expect(resetState.currentPhase).toBe('idle');
    expect(resetState.steps).toEqual([]);
    expect(resetState.approvalAction).toBeNull();
  });
});
