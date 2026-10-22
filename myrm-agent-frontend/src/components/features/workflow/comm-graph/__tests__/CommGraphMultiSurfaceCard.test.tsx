import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { CommGraphMultiSurfaceCard } from '../CommGraphMultiSurfaceCard';
import { useCommGraphStore } from '../useCommGraphStore';

describe('CommGraphMultiSurfaceCard', () => {
  beforeEach(() => {
    act(() => {
      useCommGraphStore.getState().resetState();
    });
  });

  it('初始状态下渲染空状态卡片，并展示多智能体流水线概览', () => {
    render(<CommGraphMultiSurfaceCard />);

    expect(screen.getByText('多智能体协同通讯图 (Comm-Graph)')).toBeInTheDocument();
    expect(
      screen.getByText(/清晰空状态引导 • 实时\/历史双向游标记忆防丢失/)
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByTestId('recorded-events-count')).toHaveTextContent('已记录事件: 0');
  });

  it('点击注入协同事件按钮能够将空状态平滑切换为时间轴轨道', () => {
    render(<CommGraphMultiSurfaceCard />);

    const injectBtn = screen.getByRole('button', { name: '注入协同事件' });
    act(() => {
      fireEvent.click(injectBtn);
    });

    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByText('协同流水线事件 (1)')).toBeInTheDocument();
    expect(screen.getByText('步骤 #1')).toBeInTheDocument();
    expect(screen.getByTestId('recorded-events-count')).toHaveTextContent('已记录事件: 1');
  });

  it('点击清空重置按钮能够切回空状态且重置流水线初始化态', () => {
    render(<CommGraphMultiSurfaceCard />);

    const injectBtn = screen.getByRole('button', { name: '注入协同事件' });
    act(() => {
      fireEvent.click(injectBtn);
    });
    expect(screen.getByTestId('recorded-events-count')).toHaveTextContent('已记录事件: 1');

    const resetBtn = screen.getByRole('button', { name: '清空重置' });
    act(() => {
      fireEvent.click(resetBtn);
    });

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByTestId('recorded-events-count')).toHaveTextContent('已记录事件: 0');
  });
});
