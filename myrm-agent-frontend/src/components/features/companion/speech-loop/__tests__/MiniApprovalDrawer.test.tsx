import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MiniApprovalDrawer } from '../MiniApprovalDrawer';
import { usePetSpeechLoopStore } from '../usePetSpeechLoopStore';
import { ApprovalAction } from '../petSpeechLoopTypes';

describe('MiniApprovalDrawer', () => {
  beforeEach(() => {
    act(() => {
      usePetSpeechLoopStore.getState().reset();
    });
  });

  it('在未打开或无待拍板动作时不渲染任何 DOM', () => {
    render(<MiniApprovalDrawer />);
    expect(
      screen.queryByTestId('mini-approval-drawer')
    ).not.toBeInTheDocument();
  });

  it('正确渲染待拍板方案摘要、受影响文件与低风险标签', () => {
    const action: ApprovalAction = {
      id: 'app-01',
      summary: '微调侧边栏导航间距与高亮色彩',
      riskLevel: 'low',
      proposedFiles: ['src/components/Sidebar.tsx', 'src/styles/theme.css'],
      status: 'pending',
    };

    act(() => {
      usePetSpeechLoopStore.setState({
        isApprovalDrawerOpen: true,
        approvalAction: action,
      });
    });

    render(<MiniApprovalDrawer />);

    expect(screen.getByTestId('mini-approval-drawer')).toBeInTheDocument();
    expect(screen.getByText('贴身拍板与验收')).toBeInTheDocument();
    expect(
      screen.getByText('微调侧边栏导航间距与高亮色彩')
    ).toBeInTheDocument();
    expect(screen.getByText('低风险变更')).toBeInTheDocument();
    expect(screen.getByText('src/components/Sidebar.tsx')).toBeInTheDocument();
    expect(screen.getByText('src/styles/theme.css')).toBeInTheDocument();
  });

  it('针对高风险动作正确呈现需重点复核风险标识', () => {
    const highRiskAction: ApprovalAction = {
      id: 'app-02',
      summary: '重构底层数据库存储结构并迁移旧表',
      riskLevel: 'high',
      proposedFiles: ['src/server/db/schema.prisma'],
      status: 'pending',
    };

    act(() => {
      usePetSpeechLoopStore.setState({
        isApprovalDrawerOpen: true,
        approvalAction: highRiskAction,
      });
    });

    render(<MiniApprovalDrawer />);
    expect(screen.getByText('需重点复核')).toBeInTheDocument();
  });

  it('点击批准实施按钮调用 approveAction 并关闭抽屉', () => {
    act(() => {
      usePetSpeechLoopStore.getState().runFullCycle('快速测试一键拍板');
    });

    render(<MiniApprovalDrawer />);

    expect(screen.getByTestId('mini-approval-drawer')).toBeInTheDocument();
    const approveBtn = screen.getByRole('button', { name: /批准实施/i });

    act(() => {
      fireEvent.click(approveBtn);
    });

    expect(usePetSpeechLoopStore.getState().isApprovalDrawerOpen).toBe(false);
    expect(usePetSpeechLoopStore.getState().approvalAction?.status).toBe(
      'approved'
    );
    expect(
      screen.queryByTestId('mini-approval-drawer')
    ).not.toBeInTheDocument();
  });

  it('点击修改撤回按钮调用 rejectAction 并关闭抽屉', () => {
    act(() => {
      usePetSpeechLoopStore.getState().runFullCycle('测试撤回');
    });

    render(<MiniApprovalDrawer />);

    const rejectBtn = screen.getByRole('button', { name: /修改撤回/i });
    act(() => {
      fireEvent.click(rejectBtn);
    });

    expect(usePetSpeechLoopStore.getState().isApprovalDrawerOpen).toBe(false);
    expect(usePetSpeechLoopStore.getState().approvalAction?.status).toBe(
      'rejected'
    );
  });

  it('点击右上角关闭按钮关闭拍板面板', () => {
    act(() => {
      usePetSpeechLoopStore.getState().runFullCycle('测试关闭');
    });

    render(<MiniApprovalDrawer />);

    const closeBtn = screen.getByRole('button', { name: '关闭拍板面板' });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(usePetSpeechLoopStore.getState().isApprovalDrawerOpen).toBe(false);
  });
});
