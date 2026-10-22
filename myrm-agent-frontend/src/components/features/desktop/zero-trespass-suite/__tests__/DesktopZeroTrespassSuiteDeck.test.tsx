import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { DesktopZeroTrespassSuiteDeck } from '../DesktopZeroTrespassSuiteDeck';
import { useZeroTrespassStore } from '../useZeroTrespassStore';

describe('DesktopZeroTrespassSuiteDeck Component Suite', () => {
  beforeEach(() => {
    useZeroTrespassStore.getState().resetState();
  });

  it('renders deck header with micro delta OTA badge and three core sub-modules', () => {
    render(<DesktopZeroTrespassSuiteDeck />);

    expect(screen.getByLabelText('桌面端零越界用户授权与全链路透明沙盒套件主看板')).toBeInTheDocument();
    expect(screen.getByLabelText('零越界套件顶栏')).toBeInTheDocument();
    expect(screen.getByText('桌面端零越界授权与透明信任中枢')).toBeInTheDocument();
    expect(screen.getByText(/Zstd 微差量热更/)).toBeInTheDocument();
    expect(screen.getByText(/省流量 99\.98%/)).toBeInTheDocument();

    // 验证三个子模块
    expect(screen.getByLabelText('零越界自启动与常驻后台透明监控看板')).toBeInTheDocument();
    expect(screen.getByLabelText('Token成本预算沙盒与真实模型防降级遥测')).toBeInTheDocument();
    expect(screen.getByLabelText('帮你省了哪一步价值量化与诚实能力边界卡片')).toBeInTheDocument();
  });

  it('toggles autostart authorization switch in daemon HUD', () => {
    render(<DesktopZeroTrespassSuiteDeck />);

    expect(screen.getByText('开机自启已禁用 (系统保护)')).toBeInTheDocument();
    const switchBtn = screen.getByRole('button', { name: '开启开机自启动' });

    fireEvent.click(switchBtn);
    expect(useZeroTrespassStore.getState().autostartAuth).toBe('granted');
    expect(screen.getByText('已显式授权开机自启')).toBeInTheDocument();

    const switchOffBtn = screen.getByRole('button', { name: '关闭开机自启动' });
    fireEvent.click(switchOffBtn);
    expect(useZeroTrespassStore.getState().autostartAuth).toBe('denied');
  });

  it('triggers kill and clean to terminate background zombie daemon', () => {
    render(<DesktopZeroTrespassSuiteDeck />);

    const killBtn = screen.getByRole('button', { name: '彻底清理退出后台进程' });
    fireEvent.click(killBtn);

    expect(useZeroTrespassStore.getState().daemonMetrics.isZombieCleaned).toBe(true);
    expect(screen.getByText('已彻底清理')).toBeInTheDocument();
    expect(screen.getByText('已终止')).toBeInTheDocument();
  });

  it('toggles BYOK mode and verifies budget confirmation gate release', () => {
    render(<DesktopZeroTrespassSuiteDeck />);

    const byokBtn = screen.getByRole('button', { name: '切换 BYOK 自带 Key 模式' });
    fireEvent.click(byokBtn);
    expect(useZeroTrespassStore.getState().isByokActive).toBe(true);
    expect(screen.getByText('BYOK 自带 Key 零加价直通')).toBeInTheDocument();

    // 模拟触发高消耗预算闸门
    act(() => {
      useZeroTrespassStore.getState().setBudgetEstimation(300000, 1.50);
    });

    expect(screen.getByText(/本次长任务预估消耗 \(\$1\.50\) 超过预设闸门 \(\$0\.50\)/)).toBeInTheDocument();

    const confirmGateBtn = screen.getByRole('button', { name: '确认高消耗预算并继续执行' });
    fireEvent.click(confirmGateBtn);

    expect(useZeroTrespassStore.getState().costBudget.isGateConfirmed).toBe(true);
    expect(screen.queryByText(/本次长任务预估消耗/)).not.toBeInTheDocument();
  });

  it('displays anti-downgrade alert when model fraud is recorded', () => {
    render(<DesktopZeroTrespassSuiteDeck />);

    expect(screen.getByText('物理模型验签一致 (无偷梁换柱)')).toBeInTheDocument();

    act(() => {
      useZeroTrespassStore.getState().recordTelemetry({
        physicalModelId: 'qwen-2.5-7b-instruct',
        claimedModelId: 'qwen-max-2026-latest',
        provider: 'Hidden Low-Cost Proxy',
        latencyMs: 95,
      });
    });

    expect(screen.getByText('检测到模型暗降告警！')).toBeInTheDocument();
    expect(screen.getByText('qwen-2.5-7b-instruct')).toBeInTheDocument();
  });

  it('renders step-saver details and honest capability boundary notice', () => {
    render(<DesktopZeroTrespassSuiteDeck />);

    expect(screen.getByText(/预计节省人工耗时: 35 分钟/)).toBeInTheDocument();
    expect(screen.getByText('自动跨 3 个业务系统提取合同数据')).toBeInTheDocument();
    expect(screen.getByText('完成 45 行公式对齐与财务损益测算')).toBeInTheDocument();
    expect(screen.getByText('生成结构化 Markdown 交付排版')).toBeInTheDocument();
    expect(screen.getByText('诚实能力边界声明 (Honest Capability Boundary)')).toBeInTheDocument();
    expect(screen.getByText(/当前模型上下文窗口为 200K/)).toBeInTheDocument();
  });
});
