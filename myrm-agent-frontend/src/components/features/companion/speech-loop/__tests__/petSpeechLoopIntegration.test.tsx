import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { PetSpeechLoopOverlay } from '../PetSpeechLoopOverlay';
import { usePetSpeechLoopStore } from '../usePetSpeechLoopStore';

describe('PetSpeechLoop Integration End-to-End', () => {
  beforeEach(() => {
    act(() => {
      usePetSpeechLoopStore.getState().reset();
    });
  });

  it('完整走通：点击麦克风唤醒 -> 语音输入 -> 自主四阶流转 -> 侧边抽屉拍板批准全闭环', () => {
    render(<PetSpeechLoopOverlay />);

    expect(screen.getByTestId('pet-speech-loop-overlay')).toBeInTheDocument();
    expect(screen.getByTestId('pet-sprite-container')).toBeInTheDocument();

    // 1. 点击麦克风唤醒
    const micBtn = screen.getByRole('button', {
      name: '开启语音免打字唤醒',
    });
    act(() => {
      fireEvent.click(micBtn);
    });

    expect(usePetSpeechLoopStore.getState().voiceStatus).toBe('listening');
    expect(screen.getByTestId('pet-speech-bubble')).toBeInTheDocument();
    expect(screen.getByText(/我在听/)).toBeInTheDocument();

    // 2. 模拟语音流式片段传入
    act(() => {
      usePetSpeechLoopStore
        .getState()
        .feedVoiceInput('帮我做一个自媒体', false);
    });
    expect(screen.getByText(/自媒体/)).toBeInTheDocument();

    // 3. 静音截断并确认最终完整指令
    act(() => {
      usePetSpeechLoopStore
        .getState()
        .feedVoiceInput('帮我做一个自媒体工作台', true);
    });

    const store = usePetSpeechLoopStore.getState();
    expect(store.currentPhase).toBe('planning');
    expect(store.steps).toHaveLength(4);
    expect(screen.getByTestId('pet-loop-stage-badge')).toBeInTheDocument();

    // 4. 逐步自主推演：Plan -> Code -> Exec -> Review
    act(() => {
      usePetSpeechLoopStore.getState().advanceToNextPhase(); // -> coding
    });
    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('coding');

    act(() => {
      usePetSpeechLoopStore.getState().advanceToNextPhase(); // -> executing
    });
    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('executing');

    act(() => {
      usePetSpeechLoopStore.getState().advanceToNextPhase(); // -> reviewing
    });
    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('reviewing');

    // 5. 侧边微型拍板抽屉自动弹出
    expect(screen.getByTestId('mini-approval-drawer')).toBeInTheDocument();
    expect(screen.getByText('贴身拍板与验收')).toBeInTheDocument();

    // 6. 用户一键拍板批准
    const approveBtn = screen.getByRole('button', { name: /批准实施/i });
    act(() => {
      fireEvent.click(approveBtn);
    });

    // 7. 抽屉关闭，状态变为 completed，桌宠开始庆祝
    expect(
      screen.queryByTestId('mini-approval-drawer')
    ).not.toBeInTheDocument();
    const finalState = usePetSpeechLoopStore.getState();
    expect(finalState.currentPhase).toBe('completed');
    expect(finalState.petMood).toBe('celebrating');
    expect(finalState.isWiggling).toBe(true);
  });

  it('支持在输入框键入模拟语音并使用工具条单步推演和重置', () => {
    render(<PetSpeechLoopOverlay />);

    const input = screen.getByPlaceholderText('对着桌宠说点什么…');
    const submitBtn = screen.getByRole('button', {
      name: '发送语音模拟指令',
    });

    fireEvent.change(input, { target: { value: '生成每周代码周报' } });
    act(() => {
      fireEvent.click(submitBtn);
    });

    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('planning');
    expect(screen.getByText('推进一步')).toBeInTheDocument();

    // 单步推进一步
    const stepBtn = screen.getByRole('button', { name: /推进一步/i });
    act(() => {
      fireEvent.click(stepBtn);
    });
    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('coding');

    // 点击重置
    const resetBtn = screen.getByRole('button', { name: /重置/i });
    act(() => {
      fireEvent.click(resetBtn);
    });
    expect(usePetSpeechLoopStore.getState().currentPhase).toBe('idle');
    expect(usePetSpeechLoopStore.getState().steps).toEqual([]);
  });
});
