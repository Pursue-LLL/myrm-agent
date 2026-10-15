import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TriSurfaceTaskIndicator } from '../TriSurfaceTaskIndicator';
import { useDockableWorkbenchStore } from '../useDockableWorkbenchStore';

describe('TriSurfaceTaskIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDockableWorkbenchStore.getState().resetStore();
    useDockableWorkbenchStore.setState({
      currentTask: {
        taskId: 't-test-1',
        status: 'running',
        currentTool: 'write_file',
        stepIndex: 2,
        totalSteps: 5,
        epoch: 2,
        sequenceNo: 15,
        progressPercentage: 40,
        lastMessage: '正在写入模块',
      },
    });
  });

  it('当 currentTask 为空时应安全返回 null', () => {
    useDockableWorkbenchStore.setState({ currentTask: null });
    const { container } = render(<TriSurfaceTaskIndicator mode="collapsed_row" />);
    expect(container.firstChild).toBeNull();
  });

  it('collapsed_row 折叠微行应正确渲染状态与调用工具', () => {
    const handleOpenDetail = vi.fn();
    render(
      <TriSurfaceTaskIndicator
        mode="collapsed_row"
        onOpenDetail={handleOpenDetail}
      />
    );

    expect(screen.getByTestId('tri-surface-collapsed-row')).toBeInTheDocument();
    expect(screen.getByText('正在执行')).toBeInTheDocument();
    expect(screen.getByText(/write_file/)).toBeInTheDocument();
    expect(screen.getByText('2 / 5 步 (40%)')).toBeInTheDocument();

    const detailBtn = screen.getByRole('button', { name: '详情' });
    fireEvent.click(detailBtn);
    expect(handleOpenDetail).toHaveBeenCalledTimes(1);
  });

  it('expanded_card 展开卡片应正确渲染进度条与步骤', () => {
    render(<TriSurfaceTaskIndicator mode="expanded_card" />);

    expect(screen.getByTestId('tri-surface-expanded-card')).toBeInTheDocument();
    expect(screen.getByText(/任务执行看板/)).toBeInTheDocument();
    expect(screen.getByText('2 / 5 步 (40%)')).toBeInTheDocument();
    expect(screen.getByText(/正在执行步骤 \[2\]/)).toBeInTheDocument();
    expect(screen.getByText(/任务标识: t-test-1/)).toBeInTheDocument();
    expect(screen.getByText(/连接代次: E2/)).toBeInTheDocument();
  });

  it('detail_drawer 侧栏抽屉应正确渲染代次与详细指标', () => {
    render(<TriSurfaceTaskIndicator mode="detail_drawer" />);

    expect(screen.getByTestId('tri-surface-detail-drawer')).toBeInTheDocument();
    expect(screen.getByText('侧栏任务详情全景')).toBeInTheDocument();
    expect(screen.getByText('Seq #15')).toBeInTheDocument();
    expect(screen.getByText('2 / 5 步 (40%)')).toBeInTheDocument();
    expect(screen.getByText('write_file')).toBeInTheDocument();
  });
});
