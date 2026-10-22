import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { UnifiedSpecialtyWorkplaceHub } from '../UnifiedSpecialtyWorkplaceHub';

describe('UnifiedSpecialtyWorkplaceHub', () => {
  it('renders workplace hub with title and quick companion button', () => {
    render(<UnifiedSpecialtyWorkplaceHub />);

    expect(screen.getByText('数字员工专业套件工作台')).toBeDefined();
    expect(screen.getByRole('button', { name: /连接移动伴侣/i })).toBeDefined();
    expect(screen.getByText(/专家智能体/)).toBeDefined();
    expect(screen.getByText(/企业连接器/)).toBeDefined();
    expect(screen.getByText(/统一定时任务/)).toBeDefined();
  });

  it('renders specialty suites tab and handles suite card click', () => {
    const onSelectSuite = vi.fn();
    render(<UnifiedSpecialtyWorkplaceHub onSelectSuite={onSelectSuite} />);

    expect(screen.getByText('财务与税务审计专家')).toBeDefined();
    expect(screen.getByText('法务合规风控专家')).toBeDefined();
    expect(screen.getByText('商业数据智能专家')).toBeDefined();
    expect(screen.getByText('全栈工程自进化专家')).toBeDefined();

    const financeCard = screen.getByText('财务与税务审计专家');
    fireEvent.click(financeCard);

    expect(onSelectSuite).toHaveBeenCalledTimes(1);
    expect(onSelectSuite.mock.calls[0][0].domain).toBe('finance');
  });

  it('switches to connectors tab and shows channel statuses', () => {
    render(<UnifiedSpecialtyWorkplaceHub />);

    const connectorsTab = screen.getByRole('button', { name: /企业连接器/ });
    fireEvent.click(connectorsTab);

    expect(screen.getByText('飞书协作通道')).toBeDefined();
    expect(screen.getByText('企业微信工作台')).toBeDefined();
    expect(screen.getByText('钉钉群机器人')).toBeDefined();
  });

  it('switches to cron tab and shows execution target badges', () => {
    render(<UnifiedSpecialtyWorkplaceHub />);

    const cronTab = screen.getByRole('button', { name: /统一定时任务/ });
    fireEvent.click(cronTab);

    expect(screen.getByText('每日早报与代码库健康巡检')).toBeDefined();
    expect(screen.getByText('云端常驻')).toBeDefined();
    expect(screen.getByText('本地开发沙箱构建缓存修剪')).toBeDefined();
    expect(screen.getByText('本机设备')).toBeDefined();
  });

  it('opens zero-config pairing modal when clicking companion button', () => {
    render(<UnifiedSpecialtyWorkplaceHub />);

    const pairBtn = screen.getByRole('button', { name: /连接移动伴侣/i });
    fireEvent.click(pairBtn);

    expect(screen.getByText('免配置移动伴侣扫码网关')).toBeDefined();
  });
});
