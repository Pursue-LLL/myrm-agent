import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MultiModelSplitArenaView } from '../MultiModelSplitArenaView';
import { useArenaStore } from '../useArenaStore';

describe('MultiModelSplitArenaView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useArenaStore.getState().resetStore();
  });

  it('分栏竞技场应渲染标题、默认 2 个模型分栏及其性能指标', () => {
    render(<MultiModelSplitArenaView />);

    expect(screen.getByText('多模型分栏对照竞技场')).toBeInTheDocument();
    expect(screen.getByTestId('arena-column-claude-3-7-thinking')).toBeInTheDocument();
    expect(screen.getByTestId('arena-column-deepseek-r1')).toBeInTheDocument();
  });

  it('当模型流产生思考链时，点击折叠按钮能展开思考链内容', () => {
    useArenaStore.getState().updateStream('deepseek-r1', {
      reasoningText: '思考过程：分析当前算法时间复杂度，得出优化路径...',
      contentText: '这是经过深度思考后的结论',
    });

    render(<MultiModelSplitArenaView />);

    const toggleBtn = screen.getByRole('button', { name: /深度思考链/i });
    expect(toggleBtn).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.getByText(/分析当前算法时间复杂度/)).toBeInTheDocument();
    expect(screen.getByText('这是经过深度思考后的结论')).toBeInTheDocument();
  });

  it('当已完成采纳时应高亮展示已采纳徽章', () => {
    useArenaStore.getState().adoptSingleSolution('claude-3-7-thinking');
    render(<MultiModelSplitArenaView />);

    expect(screen.getByText(/已权威采纳模型/)).toBeInTheDocument();
  });

  it('当模型流产生错误时应安全渲染错误提示', () => {
    useArenaStore.getState().updateStream('claude-3-7-thinking', {
      error: '模型推理并发配额超限，请稍后重试',
    });

    render(<MultiModelSplitArenaView />);
    expect(screen.getByText('模型推理并发配额超限，请稍后重试')).toBeInTheDocument();
  });
});
