import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { LiveSandboxDualViewportEngine } from '../LiveSandboxDualViewportEngine';
import { useSandboxDualViewportStore } from '../useSandboxDualViewportStore';

describe('LiveSandboxDualViewportEngine Suite', () => {
  beforeEach(() => {
    useSandboxDualViewportStore.getState().resetState();
  });

  it('renders engine container with header, design system sniffer, and preview area', () => {
    render(<LiveSandboxDualViewportEngine />);

    expect(screen.getByLabelText('沙箱双视口视觉自闭环验证与控制台自愈引擎')).toBeInTheDocument();
    expect(screen.getByLabelText('双视口验证顶栏')).toBeInTheDocument();
    expect(screen.getByLabelText('前置设计系统与API契约嗅探看板')).toBeInTheDocument();
    expect(screen.getByRole('main', { name: '双视口实时预览主舞台' })).toBeInTheDocument();
    expect(screen.getByLabelText('控制台与网络请求零容忍门禁')).toBeInTheDocument();

    // 默认是桌面端预览
    expect(screen.getByLabelText('桌面端视口预览 (1280x800)')).toBeInTheDocument();
  });

  it('switches viewport modes via header buttons', () => {
    render(<LiveSandboxDualViewportEngine />);

    const mobileBtn = screen.getByRole('button', { name: '切换至移动端视口 (375px)' });
    const sideBySideBtn = screen.getByRole('button', { name: '切换至双视口并排对比模式' });
    const desktopBtn = screen.getByRole('button', { name: '切换至桌面端视口 (1280px)' });

    // 切换至移动端
    fireEvent.click(mobileBtn);
    expect(useSandboxDualViewportStore.getState().activeMode).toBe('mobile');
    expect(screen.getByLabelText('移动端视口预览 (375x667)')).toBeInTheDocument();
    expect(screen.queryByLabelText('桌面端视口预览 (1280x800)')).not.toBeInTheDocument();

    // 切换至双屏并排
    fireEvent.click(sideBySideBtn);
    expect(useSandboxDualViewportStore.getState().activeMode).toBe('side_by_side');
    expect(screen.getByLabelText('移动端视口预览 (375x667)')).toBeInTheDocument();
    expect(screen.getByLabelText('桌面端视口预览 (1280x800)')).toBeInTheDocument();

    // 切换回桌面端
    fireEvent.click(desktopBtn);
    expect(useSandboxDualViewportStore.getState().activeMode).toBe('desktop');
  });

  it('toggles design system asset enforcement in sniffer badge', () => {
    render(<LiveSandboxDualViewportEngine />);

    expect(screen.getByText('StandardDataTable')).toBeInTheDocument();
    expect(screen.getByText('AccessibleModalDialog')).toBeInTheDocument();
    expect(screen.getByText('unifiedApiClient')).toBeInTheDocument();

    const toggleBtn = screen.getByRole('button', { name: '切换 StandardDataTable 强制约束' });
    fireEvent.click(toggleBtn);

    const asset = useSandboxDualViewportStore.getState().designAssets.find((a) => a.id === 'ds-table');
    expect(asset?.isEnforced).toBe(false);
  });

  it('captures errors and drives self-healing loop in HUD', () => {
    render(<LiveSandboxDualViewportEngine />);

    // 初始状态清洁
    expect(screen.getByText('控制台门禁清洁 (Zero Error & 404)')).toBeInTheDocument();

    // 注入控制台报错
    act(() => {
      useSandboxDualViewportStore.getState().addConsoleLog({
        level: 'error',
        message: 'Uncaught TypeError: items.map is not a function',
        stack: 'TypeError: items.map is not a function at UserList.tsx:18',
      });
    });

    expect(screen.getByText(/拦截到 1 处隐性异常/)).toBeInTheDocument();
    expect(screen.getAllByText(/items\.map is not a function/).length).toBeGreaterThan(0);

    // 点击“原地自愈修正”
    const healBtn = screen.getByRole('button', { name: '触发原地视觉与控制台自愈' });
    fireEvent.click(healBtn);

    expect(useSandboxDualViewportStore.getState().healingCycle.status).toBe('healing_prompt_injected');
    expect(screen.getByText(/自愈提示已注入 · 迭代 1\/3/)).toBeInTheDocument();

    // 推进重编译
    const advanceBtn = screen.getByRole('button', { name: '下一步重编译' });
    fireEvent.click(advanceBtn);
    expect(screen.getByText('沙箱重新编译热重载中...')).toBeInTheDocument();

    // 标记验证全绿
    const verifyBtn = screen.getByRole('button', { name: '验证全绿' });
    fireEvent.click(verifyBtn);
    expect(screen.getByText('双视口自愈验证通过 · 零错误白屏')).toBeInTheDocument();
  });

  it('clears errors and anomalies via clean button', () => {
    render(<LiveSandboxDualViewportEngine />);

    act(() => {
      useSandboxDualViewportStore.getState().addNetworkAnomaly({
        url: '/static/hero.jpg',
        method: 'GET',
        status: 404,
        statusText: 'Not Found',
      });
    });

    const clearBtn = screen.getByRole('button', { name: '清空当前所有异常记录' });
    fireEvent.click(clearBtn);

    expect(useSandboxDualViewportStore.getState().networkAnomalies).toHaveLength(0);
  });
});
