import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { InlineReasoningTimelineBox } from '../InlineReasoningTimelineBox';
import { useThinkingBudgetStore } from '../useThinkingBudgetStore';

describe('InlineReasoningTimelineBox', () => {
  beforeEach(() => {
    useThinkingBudgetStore.getState().reset();
  });

  it('renders nothing when rawContent is empty and isThinking is false', () => {
    useThinkingBudgetStore.setState({ rawContent: '', isThinking: false });
    const { container } = render(<InlineReasoningTimelineBox />);

    expect(container.firstChild).toBeNull();
  });

  it('renders in-progress thinking state with pulsing timer', () => {
    useThinkingBudgetStore.setState({
      isThinking: true,
      totalElapsedSec: 6.4,
      thinkingTokens: 1200,
      rawContent: '思考推演中...',
    });

    render(<InlineReasoningTimelineBox />);

    expect(screen.getByText('深度思考推演中...')).toBeInTheDocument();
    expect(screen.getByText('6.4s')).toBeInTheDocument();
    expect(screen.getByText('1.2k 推理 Tokens')).toBeInTheDocument();
  });

  it('renders completed thinking state in compact collapsed mode and toggles expansion', () => {
    render(<InlineReasoningTimelineBox />);

    expect(screen.getByText('已深度思考完成')).toBeInTheDocument();
    expect(screen.getByText('14.8s')).toBeInTheDocument();
    expect(screen.getByText('4.2k 推理 Tokens')).toBeInTheDocument();
    expect(screen.getByText('展开详情')).toBeInTheDocument();

    // 点击展开
    const toggleBtn = screen.getByRole('button', { name: '展开或收起深度思考思维链' });
    fireEvent.click(toggleBtn);

    expect(screen.getByText(/推理阶段里程碑/)).toBeInTheDocument();
    expect(screen.getByText(/阶段 1/)).toBeInTheDocument();
    expect(screen.getByText('收起思维链')).toBeInTheDocument();
  });

  it('toggles individual stage details and copies reasoning content', async () => {
    // 模拟 navigator.clipboard
    const mockWriteText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: mockWriteText,
      },
    });

    useThinkingBudgetStore.setState({ isExpanded: true });
    render(<InlineReasoningTimelineBox />);

    // 点击阶段摘要卡片展开阶段原始论证
    const stage1Card = screen.getByText(/业务峰值 QPS 为 50,000/).closest('div[role="presentation"]');
    expect(stage1Card).toBeInTheDocument();

    if (stage1Card) {
      act(() => {
        fireEvent.click(stage1Card);
      });
    }

    // 点击复制思维链
    const copyBtn = screen.getByText('复制思维链');
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(mockWriteText).toHaveBeenCalled();
  });
});
