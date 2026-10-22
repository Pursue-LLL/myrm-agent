import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VoiceDirectInputBubble } from '../VoiceDirectInputBubble';
import { useDesktopPetPulseStore } from '../useDesktopPetPulseStore';

describe('VoiceDirectInputBubble', () => {
  beforeEach(() => {
    useDesktopPetPulseStore.getState().resetAll();
  });

  it('当未激活语音直通时不渲染任何内容', () => {
    useDesktopPetPulseStore.setState({ isVoiceInputActive: false });
    const { container } = render(<VoiceDirectInputBubble />);
    expect(container.firstChild).toBeNull();
  });

  it('激活时渲染语音气泡、声波可视化容器与指令输入框', () => {
    useDesktopPetPulseStore.setState({ isVoiceInputActive: true });
    render(<VoiceDirectInputBubble />);

    expect(
      screen.getByTestId('voice-direct-input-bubble')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('voice-waveform-container')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('voice-prompt-textarea')
    ).toBeInTheDocument();
  });

  it('输入指令并点击直通派发按钮，触发派发回调并关闭气泡', () => {
    const handleDispatch = vi.fn();
    useDesktopPetPulseStore.setState({ isVoiceInputActive: true });
    render(<VoiceDirectInputBubble onDispatchTask={handleDispatch} />);

    const textarea = screen.getByTestId('voice-prompt-textarea');
    fireEvent.change(textarea, {
      target: { value: '拉取最新日志并分析异常' },
    });

    const dispatchBtn = screen.getByTestId('dispatch-voice-task-btn');
    expect(dispatchBtn).not.toBeDisabled();

    fireEvent.click(dispatchBtn);
    expect(handleDispatch).toHaveBeenCalledTimes(1);
    expect(handleDispatch).toHaveBeenCalledWith(
      expect.objectContaining({
        prompt: '拉取最新日志并分析异常',
        autoRun: true,
      })
    );
    expect(
      useDesktopPetPulseStore.getState().isVoiceInputActive
    ).toBe(false);
  });

  it('点击关闭按钮停止录音并收起面板', () => {
    const handleClose = vi.fn();
    useDesktopPetPulseStore.setState({ isVoiceInputActive: true });
    render(<VoiceDirectInputBubble onClose={handleClose} />);

    const closeBtn = screen.getByTestId('close-voice-bubble-btn');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(
      useDesktopPetPulseStore.getState().isVoiceInputActive
    ).toBe(false);
  });
});
