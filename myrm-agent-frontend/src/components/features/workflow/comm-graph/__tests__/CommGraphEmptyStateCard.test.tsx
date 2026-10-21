import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { CommGraphEmptyStateCard } from '../CommGraphEmptyStateCard';
import { useCommGraphStore } from '../useCommGraphStore';

describe('CommGraphEmptyStateCard', () => {
  beforeEach(() => {
    act(() => {
      useCommGraphStore.getState().resetState();
    });
  });

  it('渲染无障碍状态 role=status，展示流水线正在建立链路提示且无误导性 Live 徽标', () => {
    render(<CommGraphEmptyStateCard />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/正在建立多智能体全双工协同链路/)).toBeInTheDocument();
    expect(screen.getByText(/误导性的 Live 实时徽标已自动隐藏/)).toBeInTheDocument();
    // 严格确保空状态下没有任何 Live 高亮字样
    expect(screen.queryByText(/Live 实时跟随中/)).toBeNull();
  });

  it('当 isPipelineInitializing 为 false 时，切换为暂无协同事件占位', () => {
    act(() => {
      useCommGraphStore.getState().setPipelineInitializing(false);
    });

    render(<CommGraphEmptyStateCard />);
    expect(screen.getByText('暂无协同事件 (No events yet)')).toBeInTheDocument();
  });

  it('点击模拟触发第一轮协同通讯能够成功向 Store 注入事件', () => {
    render(<CommGraphEmptyStateCard />);

    const seedBtn = screen.getByRole('button', {
      name: '模拟触发第一轮协同通讯',
    });
    act(() => {
      fireEvent.click(seedBtn);
    });

    const events = useCommGraphStore.getState().events;
    expect(events.length).toBe(1);
    expect(events[0].fromAgent).toBe('CoordinatorAgent (协调总管)');
    expect(events[0].action).toBe('dispatch_subtask');
  });
});
