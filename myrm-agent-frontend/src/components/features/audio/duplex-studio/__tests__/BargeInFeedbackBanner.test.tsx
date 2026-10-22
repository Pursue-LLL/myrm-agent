import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { BargeInFeedbackBanner } from '../BargeInFeedbackBanner';
import { useDuplexVoiceStore } from '../useDuplexVoiceStore';

describe('BargeInFeedbackBanner', () => {
  beforeEach(() => {
    act(() => {
      useDuplexVoiceStore.getState().reset();
    });
  });

  it('在无打断事件时不渲染任何节点', () => {
    render(<BargeInFeedbackBanner />);
    expect(
      screen.queryByTestId('barge-in-feedback-banner')
    ).not.toBeInTheDocument();
  });

  it('发生随时插话打断后正确呈现打断标题、截断内容与自愈说明', () => {
    act(() => {
      useDuplexVoiceStore.setState({
        bargeInState: {
          active: true,
          interruptedAt: Date.now(),
          interruptedAgentMessage: '正在为您编写常规表格组件',
          userInterruptionSnippet: '改为甘特图视图',
          healedContextPreview: '上下文自愈成功',
        },
      });
    });

    render(<BargeInFeedbackBanner />);

    expect(
      screen.getByTestId('barge-in-feedback-banner')
    ).toBeInTheDocument();
    expect(
      screen.getByText('全双工实时插话打断生效 (Zero-Latency Barge-In)')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/正在为您编写常规表格组件/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/改为甘特图视图/)
    ).toBeInTheDocument();
    expect(
      screen.getByText('上下文已无感平滑自愈，直接无缝执行最新纠偏意图')
    ).toBeInTheDocument();
  });

  it('点击关闭按钮能够隐藏打断反馈横幅', () => {
    act(() => {
      useDuplexVoiceStore.setState({
        bargeInState: {
          active: true,
          interruptedAt: Date.now(),
          interruptedAgentMessage: '输出中',
          userInterruptionSnippet: '停一下',
          healedContextPreview: '',
        },
      });
    });

    render(<BargeInFeedbackBanner />);

    const closeBtn = screen.getByRole('button', { name: '关闭打断反馈' });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(
      screen.queryByTestId('barge-in-feedback-banner')
    ).not.toBeInTheDocument();
    expect(useDuplexVoiceStore.getState().bargeInState).toBeNull();
  });
});
