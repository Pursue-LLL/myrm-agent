import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MobileRemoteSteeringBar } from '../MobileRemoteSteeringBar';
import { useMobileCompanionStore } from '../useMobileCompanionStore';

describe('MobileRemoteSteeringBar', () => {
  beforeEach(() => {
    useMobileCompanionStore.setState({
      activeTask: {
        sessionId: 'test-session-123456',
        taskName: '自动化报表生成长任务',
        phase: 'executing',
        progress: 60,
        estimatedSecondsRemaining: 180,
        highSnrSummary: ['已解析 Schema', '已连接数据库'],
        artifacts: [],
        pendingApproval: null,
      },
      isRemoteSteeringOpen: false,
    });
  });

  it('renders default bar with toggle trigger', () => {
    render(<MobileRemoteSteeringBar />);
    expect(screen.getByTestId('mobile-remote-steering-bar')).toBeInTheDocument();
    expect(screen.getByText('手机随行遥控微调')).toBeInTheDocument();
    expect(screen.getByText('WebSocket 实时信道已就绪')).toBeInTheDocument();
  });

  it('toggles remote steering panel when toggle button is clicked', () => {
    render(<MobileRemoteSteeringBar />);
    const toggleBtn = screen.getByText('手机随行遥控微调');
    fireEvent.click(toggleBtn);
    expect(useMobileCompanionStore.getState().isRemoteSteeringOpen).toBe(true);
  });

  it('allows sending remote steering text via input', () => {
    useMobileCompanionStore.setState({ isRemoteSteeringOpen: true });
    render(<MobileRemoteSteeringBar />);

    expect(screen.getByText('随行非打断微调 (主任务沙箱步间平滑吸收)')).toBeInTheDocument();

    // Form input submission
    const input = screen.getByPlaceholderText('如：增加导出 Excel 按钮、调整计算系数为 1.2...');
    fireEvent.change(input, { target: { value: '提高重试次数为 5 次' } });
    const sendBtn = screen.getByRole('button', { name: /发送/i });
    fireEvent.click(sendBtn);

    const updatedSummary = useMobileCompanionStore.getState().activeTask?.highSnrSummary;
    expect(updatedSummary?.some((s) => s.includes('提高重试次数为 5 次'))).toBe(true);
    expect(useMobileCompanionStore.getState().isRemoteSteeringOpen).toBe(false);
  });

  it('allows sending remote steering via quick chip', () => {
    useMobileCompanionStore.setState({ isRemoteSteeringOpen: true });
    render(<MobileRemoteSteeringBar />);

    const quickChipBtn = screen.getByText('+ 增加 Excel 导出');
    fireEvent.click(quickChipBtn);
    const summary = useMobileCompanionStore.getState().activeTask?.highSnrSummary;
    expect(summary?.some((s) => s.includes('增加 Excel 导出功能'))).toBe(true);
    expect(useMobileCompanionStore.getState().isRemoteSteeringOpen).toBe(false);
  });

  it('handles high risk pending approval with approve and reject actions', () => {
    useMobileCompanionStore.setState({
      activeTask: {
        sessionId: 'test-session-123456',
        taskName: '自动化报表生成长任务',
        phase: 'waiting_approval',
        progress: 75,
        estimatedSecondsRemaining: 90,
        highSnrSummary: ['等待高危授权'],
        artifacts: [],
        pendingApproval: {
          id: 'appr-1',
          toolName: 'shell_execute',
          riskLevel: 'high',
          description: '尝试在生产沙箱执行 rm -rf 临时缓存',
          params: { command: 'rm -rf /tmp/cache' },
          timestamp: Date.now(),
        },
      },
    });

    render(<MobileRemoteSteeringBar />);
    expect(screen.getByText('沙箱待审批操作')).toBeInTheDocument();
    expect(screen.getByText('HIGH RISK')).toBeInTheDocument();
    expect(screen.getByText('尝试在生产沙箱执行 rm -rf 临时缓存')).toBeInTheDocument();
    expect(screen.getByText('rm -rf /tmp/cache')).toBeInTheDocument();

    // 点击授权继续
    const approveBtn = screen.getByText('授权继续');
    fireEvent.click(approveBtn);
    expect(useMobileCompanionStore.getState().activeTask?.pendingApproval).toBeFalsy();
  });

  it('handles rejection flow with custom reject reason', () => {
    useMobileCompanionStore.setState({
      activeTask: {
        sessionId: 'test-session-123456',
        taskName: '自动化报表生成长任务',
        phase: 'waiting_approval',
        progress: 75,
        estimatedSecondsRemaining: 90,
        highSnrSummary: ['等待高危授权'],
        artifacts: [],
        pendingApproval: {
          id: 'appr-2',
          toolName: 'shell_execute',
          riskLevel: 'critical',
          description: '尝试修改数据库 Schema',
          params: { command: 'ALTER TABLE users DROP COLUMN token' },
          timestamp: Date.now(),
        },
      },
    });

    render(<MobileRemoteSteeringBar />);
    const rejectBtn = screen.getByText('拒绝 / 拦截');
    fireEvent.click(rejectBtn);

    const reasonInput = screen.getByPlaceholderText('输入拦截或打回原因...');
    fireEvent.change(reasonInput, { target: { value: '禁止直接删除字段' } });

    const confirmRejectBtn = screen.getByText('确认拦截');
    fireEvent.click(confirmRejectBtn);

    expect(useMobileCompanionStore.getState().activeTask?.pendingApproval).toBeFalsy();
    const summary = useMobileCompanionStore.getState().activeTask?.highSnrSummary;
    expect(summary?.some((s) => s.includes('禁止直接删除字段'))).toBe(true);
  });
});
