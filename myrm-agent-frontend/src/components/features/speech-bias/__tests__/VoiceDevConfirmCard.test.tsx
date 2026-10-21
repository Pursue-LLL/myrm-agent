import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VoiceDevConfirmCard } from '../VoiceDevConfirmCard';
import { useSpeechBiasStore } from '../useSpeechBiasStore';

describe('VoiceDevConfirmCard', () => {
  beforeEach(() => {
    useSpeechBiasStore.getState().reset();
  });

  it('初始未听写状态下正常渲染就绪态和占位文本', () => {
    render(<VoiceDevConfirmCard />);

    expect(screen.getByTestId('voice-dev-confirm-card')).toBeInTheDocument();
    expect(screen.getByText('代码上下文感知语音听写')).toBeInTheDocument();
    expect(screen.getByText('就绪')).toBeInTheDocument();
    expect(screen.getByText('点击开始录音，说出开发需求或命令...')).toBeInTheDocument();
  });

  it('录音状态下展示录音脉冲徽标和停止听写按钮', () => {
    useSpeechBiasStore.setState({ status: 'listening' });
    render(<VoiceDevConfirmCard />);

    expect(screen.getByText('正在录音听写...')).toBeInTheDocument();
    expect(screen.getByText('停止听写')).toBeInTheDocument();
  });

  it('展示纠偏完成内容、原始语音对照与纠偏 Chip', () => {
    useSpeechBiasStore.setState({
      status: 'ready',
      rawTranscript: '用 grape 查找',
      correctedTranscript: '用 grep 查找',
      activeCorrections: [
        {
          id: 'corr-1',
          original: 'grape',
          corrected: 'grep',
          category: 'cli_tool',
          confidence: 0.95,
          startIndex: 2,
          endIndex: 6,
        },
      ],
    });

    render(<VoiceDevConfirmCard />);

    expect(screen.getByText('纠偏完毕 · 可直接发送')).toBeInTheDocument();
    expect(screen.getByText('用 grep 查找')).toBeInTheDocument();
    expect(screen.getByText('grape')).toBeInTheDocument();
    expect(screen.getByText('grep')).toBeInTheDocument();
  });

  it('点击纠偏 Chip 可触发撤销单项纠偏', () => {
    useSpeechBiasStore.setState({
      status: 'ready',
      rawTranscript: '用 grape 查找',
      correctedTranscript: '用 grep 查找',
      activeCorrections: [
        {
          id: 'corr-1',
          original: 'grape',
          corrected: 'grep',
          category: 'cli_tool',
          confidence: 0.95,
          startIndex: 2,
          endIndex: 6,
        },
      ],
    });

    render(<VoiceDevConfirmCard />);

    const chipButton = screen.getByTitle('点击撤销：grape -> grep');
    fireEvent.click(chipButton);

    expect(useSpeechBiasStore.getState().correctedTranscript).toBe('用 grape 查找');
    expect(useSpeechBiasStore.getState().activeCorrections.length).toBe(0);
  });

  it('点击发送按钮触发 onConfirmSend 回调并重置状态', () => {
    const handleConfirm = vi.fn();
    useSpeechBiasStore.setState({
      status: 'ready',
      rawTranscript: '用 grep 查找',
      correctedTranscript: '用 grep 查找',
    });

    render(<VoiceDevConfirmCard onConfirmSend={handleConfirm} />);

    const sendBtn = screen.getByText('发给智能体 (Enter)');
    fireEvent.click(sendBtn);

    expect(handleConfirm).toHaveBeenCalledWith('用 grep 查找');
    expect(useSpeechBiasStore.getState().status).toBe('idle');
  });
});
