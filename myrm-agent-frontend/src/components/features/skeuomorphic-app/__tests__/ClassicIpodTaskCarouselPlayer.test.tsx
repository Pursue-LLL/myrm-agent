import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ClassicIpodTaskCarouselPlayer } from '../ClassicIpodTaskCarouselPlayer';
import { useSkeuomorphicAppStore } from '../useSkeuomorphicAppStore';

describe('ClassicIpodTaskCarouselPlayer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSkeuomorphicAppStore.getState().resetStore();
  });

  it('应正确渲染 iPod 机身、LCD 液晶屏、状态栏与当前工件标题', () => {
    render(<ClassicIpodTaskCarouselPlayer />);

    expect(screen.getByTestId('classic-ipod-player')).toBeInTheDocument();
    expect(screen.getByText(/重构前端会话上下文数据获取模型/)).toBeInTheDocument();
    expect(screen.getByText(/Stage 3: 架构收敛/)).toBeInTheDocument();
    expect(screen.getByTestId('ipod-click-wheel')).toBeInTheDocument();
  });

  it('点击 Click Wheel 快进/快退按钮应能向前/向后切换工件', () => {
    render(<ClassicIpodTaskCarouselPlayer />);

    const nextBtn = screen.getByRole('button', { name: /下一个任务工件/i });
    fireEvent.click(nextBtn);

    expect(
      screen.getByText(/设计拟物化复古 iPod 风格任务旋转播放器/)
    ).toBeInTheDocument();

    const prevBtn = screen.getByRole('button', { name: /上一个任务工件/i });
    fireEvent.click(prevBtn);

    expect(
      screen.getByText(/重构前端会话上下文数据获取模型/)
    ).toBeInTheDocument();
  });

  it('点击中央 SELECT 或 MENU 按钮能呼出工件成果弹窗详情并关闭', () => {
    render(<ClassicIpodTaskCarouselPlayer />);

    const selectBtn = screen.getByRole('button', { name: /查看详情/i });
    fireEvent.click(selectBtn);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/产物摘要：/)).toBeInTheDocument();
    expect(screen.getByText(/Arch-Master-4o/)).toBeInTheDocument();

    const closeBtn = screen.getByRole('button', { name: /关闭详情/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('点击播放/暂停按钮能切换自动轮播状态', () => {
    render(<ClassicIpodTaskCarouselPlayer />);

    const playBtn = screen.getByRole('button', { name: /开始自动轮播/i });
    fireEvent.click(playBtn);

    expect(useSkeuomorphicAppStore.getState().autoPlay).toBe(true);

    const pauseBtn = screen.getByRole('button', { name: /暂停自动轮播/i });
    fireEvent.click(pauseBtn);

    expect(useSkeuomorphicAppStore.getState().autoPlay).toBe(false);
  });
});
