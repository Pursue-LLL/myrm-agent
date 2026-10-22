import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { ZeroInterruptionBootContainer } from '../ZeroInterruptionBootContainer';
import { useProgressiveBootStore } from '../useProgressiveBootStore';

describe('ZeroInterruptionBootContainer', () => {
  beforeEach(() => {
    act(() => {
      useProgressiveBootStore.getState().resetBootState();
    });
  });

  it('渲染极简对话启动界面、输入框与快捷场景推荐', () => {
    render(<ZeroInterruptionBootContainer />);

    expect(screen.getByText('Myrmidon 智能体工作台')).toBeInTheDocument();
    expect(screen.getByText(/零阻断极简启动 • 渐进式能力披露/)).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/输入任务需求，例如：'分析前端性能瓶颈并提出优化方案'/i)
    ).toBeInTheDocument();
    expect(screen.getByText('重构现有模块代码结构')).toBeInTheDocument();
    expect(screen.getByText('排查沙箱运行时崩溃')).toBeInTheDocument();
  });

  it('点击快捷卡片能够快速填充输入框', () => {
    render(<ZeroInterruptionBootContainer />);

    const quickCard = screen.getByText('排查沙箱运行时崩溃');
    act(() => {
      fireEvent.click(quickCard);
    });

    const input = screen.getByPlaceholderText(
      /输入任务需求，例如：'分析前端性能瓶颈并提出优化方案'/i
    );
    expect(input).toHaveValue('排查沙箱运行时崩溃');
  });

  it('渐进式披露：按需展示 standard 与 expert 面板', () => {
    render(<ZeroInterruptionBootContainer />);

    // 初始 minimal 下不出现标准与专家级复杂面板
    expect(screen.queryByText(/标准生产档能力披露/)).toBeNull();
    expect(screen.queryByText(/专家底层档深度透视/)).toBeNull();

    // 提升至 standard
    act(() => {
      useProgressiveBootStore.getState().setDisclosureTier('standard');
    });
    expect(screen.getByText(/标准生产档能力披露/)).toBeInTheDocument();
    expect(screen.getByText('代码分析诊断器')).toBeInTheDocument();

    // 提升至 expert
    act(() => {
      useProgressiveBootStore.getState().setDisclosureTier('expert');
    });
    expect(screen.getByText(/专家底层档深度透视/)).toBeInTheDocument();
    expect(screen.getByText('PTC 标准协议通道')).toBeInTheDocument();
  });

  it('测试阻断弹窗静默拦截按钮能够安全入队，不在界面形成阻断全屏 Modal', () => {
    render(<ZeroInterruptionBootContainer />);

    const testBtn = screen.getByRole('button', { name: '模拟触发侵入式弹窗' });
    act(() => {
      fireEvent.click(testBtn);
    });

    // 验证静默入队成功
    const notices = useProgressiveBootStore.getState().silencedNotices;
    expect(notices.length).toBe(1);
    expect(notices[0].title).toBe('检测到新版本插件待配置 (已静默)');
    expect(screen.getByText('1 条已静默')).toBeInTheDocument();
  });
});
