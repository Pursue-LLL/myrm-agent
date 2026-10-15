import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useDuplexVoiceStore } from '../useDuplexVoiceStore';

describe('useDuplexVoiceStore', () => {
  beforeEach(() => {
    vi.useRealTimers();
    useDuplexVoiceStore.getState().reset();
  });

  it('初始状态为待命、静音且历史记录为空', () => {
    const state = useDuplexVoiceStore.getState();
    expect(state.status).toBe('idle');
    expect(state.messages).toEqual([]);
    expect(state.currentAgentSpeech).toBe('');
    expect(state.currentUserSpeech).toBe('');
    expect(state.bargeInState).toBeNull();
    expect(state.metrics.vadActive).toBe(false);
  });

  it('能够开启和挂断全双工会话', () => {
    const store = useDuplexVoiceStore.getState();
    store.startDuplexSession();

    expect(useDuplexVoiceStore.getState().status).toBe('listening');

    store.stopDuplexSession();
    expect(useDuplexVoiceStore.getState().status).toBe('idle');
  });

  it('麦克风音量输入能够正确驱动 VAD 活性指示', () => {
    const store = useDuplexVoiceStore.getState();
    store.startDuplexSession();

    store.feedMicAudioVolume(5);
    expect(useDuplexVoiceStore.getState().metrics.vadActive).toBe(false);

    store.feedMicAudioVolume(35);
    expect(useDuplexVoiceStore.getState().metrics.vadActive).toBe(true);
    expect(useDuplexVoiceStore.getState().metrics.micVolume).toBe(35);
  });

  it('在智能体 speaking 状态下，用户声音飙升自动触发毫秒级 Barge-In 打断', () => {
    const store = useDuplexVoiceStore.getState();
    store.startDuplexSession();

    // 智能体开始播报
    store.feedAgentSpeechStream('正在为您生成全套测试用例与执行脚本…', false);
    expect(useDuplexVoiceStore.getState().status).toBe('speaking');
    expect(useDuplexVoiceStore.getState().currentAgentSpeech).toContain(
      '全套测试用例'
    );

    // 用户突然开口插话，音量达到 medium 门限 (45)
    store.feedMicAudioVolume(70);

    const interruptedState = useDuplexVoiceStore.getState();
    expect(interruptedState.status).toBe('interrupted');
    expect(interruptedState.bargeInState).not.toBeNull();
    expect(interruptedState.bargeInState?.interruptedAgentMessage).toContain(
      '全套测试用例'
    );
    expect(interruptedState.currentAgentSpeech).toBe('');
  });

  it('打断后用户输入最终文本，能够对齐沉淀为被截断的 Agent 消息和用户纠偏消息', () => {
    const store = useDuplexVoiceStore.getState();
    store.startDuplexSession();

    store.feedAgentSpeechStream('第一步是初始化数据库连接池', false);
    store.feedMicAudioVolume(60); // 触发打断

    // 用户输入完整的纠偏话语
    store.feedUserSpeechStream('不要数据库，直接用内存数据做 mock 即可', true);

    const state = useDuplexVoiceStore.getState();
    expect(state.status).toBe('processing');
    expect(state.messages).toHaveLength(2);

    expect(state.messages[0].role).toBe('agent');
    expect(state.messages[0].wasInterrupted).toBe(true);
    expect(state.messages[0].content).toBe('第一步是初始化数据库连接池');

    expect(state.messages[1].role).toBe('user');
    expect(state.messages[1].content).toBe(
      '不要数据库，直接用内存数据做 mock 即可'
    );
  });

  it('支持正常无打断的单轮发言闭环', () => {
    const store = useDuplexVoiceStore.getState();
    store.startDuplexSession();

    // 用户正常发言
    store.feedUserSpeechStream('请帮我审查代码规范', true);
    expect(useDuplexVoiceStore.getState().messages).toHaveLength(1);
    expect(useDuplexVoiceStore.getState().messages[0].role).toBe('user');

    // 智能体正常播报完毕
    store.feedAgentSpeechStream('代码审查已完成，0 报错 0 警告。', true);
    expect(useDuplexVoiceStore.getState().messages).toHaveLength(2);
    expect(useDuplexVoiceStore.getState().messages[1].role).toBe('agent');
    expect(useDuplexVoiceStore.getState().messages[1].wasInterrupted).toBeFalsy();
  });

  it('支持更新设置、关闭打断横幅、清空历史与彻底重置', () => {
    const store = useDuplexVoiceStore.getState();
    store.updateSettings({ bargeInSensitivity: 'high' });
    expect(useDuplexVoiceStore.getState().settings.bargeInSensitivity).toBe(
      'high'
    );

    store.triggerBargeIn('手动测试打断');
    expect(useDuplexVoiceStore.getState().bargeInState).not.toBeNull();

    store.dismissBargeInBanner();
    expect(useDuplexVoiceStore.getState().bargeInState).toBeNull();

    store.reset();
    expect(useDuplexVoiceStore.getState().status).toBe('idle');
    expect(useDuplexVoiceStore.getState().settings.bargeInSensitivity).toBe(
      'medium'
    );
  });
});
