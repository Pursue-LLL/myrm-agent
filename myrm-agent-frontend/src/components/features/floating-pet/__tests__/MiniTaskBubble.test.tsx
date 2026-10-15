import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MiniTaskBubble } from '../MiniTaskBubble';
import { useFloatingPetStore } from '../useFloatingPetStore';

describe('MiniTaskBubble', () => {
  beforeEach(() => {
    useFloatingPetStore.getState().reset();
  });

  it('未展开或无活跃任务时返回 null 不渲染 DOM', () => {
    useFloatingPetStore.setState({ isBubbleExpanded: false, activeTask: null });
    const { container } = render(<MiniTaskBubble />);

    expect(container.firstChild).toBeNull();
  });

  it('展开状态下正常渲染任务标题、进度条与状态摘要', () => {
    useFloatingPetStore.setState({
      isBubbleExpanded: true,
      activeTask: {
        id: 'task-test-1',
        title: '书画作品定制报价工具',
        status: 'running',
        progress: 45,
        summary: '正在生成核心计算逻辑与组件布局',
        createdAt: Date.now(),
      },
    });

    render(<MiniTaskBubble />);

    expect(screen.getByTestId('mini-task-bubble')).toBeInTheDocument();
    expect(screen.getByText('后台伴随任务')).toBeInTheDocument();
    expect(screen.getByText('书画作品定制报价工具')).toBeInTheDocument();
    expect(screen.getByText(/执行中 45%/)).toBeInTheDocument();
    expect(screen.getByText('正在生成核心计算逻辑与组件布局')).toBeInTheDocument();
  });

  it('点击查看工件详情按钮触发 onOpenMainWindow 回调', () => {
    const handleOpenMain = vi.fn();
    useFloatingPetStore.setState({
      isBubbleExpanded: true,
      activeTask: {
        id: 'task-test-2',
        title: '自动化报表导出',
        status: 'completed',
        progress: 100,
        summary: '导出完成',
        createdAt: Date.now(),
      },
    });

    render(<MiniTaskBubble onOpenMainWindow={handleOpenMain} />);

    const openBtn = screen.getByText('查看工件详情');
    fireEvent.click(openBtn);

    expect(handleOpenMain).toHaveBeenCalledWith('task-test-2');
  });

  it('支持点击收起气泡', () => {
    useFloatingPetStore.setState({
      isBubbleExpanded: true,
      activeTask: {
        id: 'task-test-3',
        title: '测试任务',
        status: 'running',
        progress: 20,
        summary: '摘要',
        createdAt: Date.now(),
      },
    });

    render(<MiniTaskBubble />);

    const closeBtn = screen.getByTitle('收起气泡');
    fireEvent.click(closeBtn);
    expect(useFloatingPetStore.getState().isBubbleExpanded).toBe(false);
  });

  it('支持点击归档清除当前任务', () => {
    useFloatingPetStore.setState({
      isBubbleExpanded: true,
      activeTask: {
        id: 'task-test-4',
        title: '测试清除任务',
        status: 'completed',
        progress: 100,
        summary: '任务完成摘要',
        createdAt: Date.now(),
      },
    });

    render(<MiniTaskBubble />);

    const clearBtn = screen.getByText('归档清除');
    fireEvent.click(clearBtn);

    expect(useFloatingPetStore.getState().activeTask).toBeNull();
    expect(useFloatingPetStore.getState().isBubbleExpanded).toBe(false);
  });
});
