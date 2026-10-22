'use client';

import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  InfraQuotaCockpit,
  InfraQuotaData,
} from '../InfraQuotaCockpit';

const mockQuotaData: InfraQuotaData = {
  userId: 'org_acme_engineering',
  isLocalMode: true,
  quotas: [
    {
      resourceType: 'active_agents',
      displayName: '活跃智能体数量',
      used: 6,
      limit: 20,
      unit: 'count',
      usagePct: 30.0,
      status: 'normal',
    },
    {
      resourceType: 'ephemeral_dbs',
      displayName: '临时工作数据库',
      used: 2,
      limit: 10,
      unit: 'count',
      usagePct: 20.0,
      status: 'normal',
    },
    {
      resourceType: 'concurrent_sandboxes',
      displayName: '并发执行沙箱',
      used: 4,
      limit: 5,
      unit: 'count',
      usagePct: 80.0,
      status: 'warning',
    },
    {
      resourceType: 'volume_storage_gb',
      displayName: '持久卷磁盘空间',
      used: 46.5,
      limit: 50.0,
      unit: 'GB',
      usagePct: 93.0,
      status: 'critical',
    },
  ],
  doctorRecommendations: [
    '持久 Volume 磁盘已占用 93.0%：建议清空历史构建临时缓存或归档冷数据。',
    '并发沙箱占位已达 80.0%：建议开启执行队列排队或复用微沙箱。',
  ],
};

describe('InfraQuotaCockpit', () => {
  it('renders cockpit header, user id, and deployment mode badge', () => {
    render(<InfraQuotaCockpit data={mockQuotaData} />);

    expect(screen.getByTestId('infra-quota-cockpit')).toBeInTheDocument();
    expect(screen.getByText('多 Agent 基础设施配额治理驾驶舱')).toBeInTheDocument();
    expect(screen.getByText('单机物理沙箱模式')).toBeInTheDocument();
    expect(screen.getByText('org_acme_engineering')).toBeInTheDocument();
  });

  it('renders 4-dimensional quota cards with metrics and progress bars', () => {
    render(<InfraQuotaCockpit data={mockQuotaData} />);

    const grid = screen.getByTestId('quota-cards-grid');
    expect(grid).toBeInTheDocument();

    expect(screen.getByText('活跃智能体数量')).toBeInTheDocument();
    expect(screen.getByText('6 / 20')).toBeInTheDocument();

    expect(screen.getByText('临时工作数据库')).toBeInTheDocument();
    expect(screen.getByText('2 / 10')).toBeInTheDocument();

    expect(screen.getByText('并发执行沙箱')).toBeInTheDocument();
    expect(screen.getByText('4 / 5')).toBeInTheDocument();

    expect(screen.getByText('持久卷磁盘空间')).toBeInTheDocument();
    expect(screen.getByText('46.5 / 50')).toBeInTheDocument();
  });

  it('renders Doctor recommendations panel with actionable advice', () => {
    render(<InfraQuotaCockpit data={mockQuotaData} />);

    const panel = screen.getByTestId('doctor-recommendations-panel');
    expect(panel).toBeInTheDocument();
    expect(screen.getByText(/持久 Volume 磁盘已占用 93.0%/)).toBeInTheDocument();
    expect(screen.getByText(/并发沙箱占位已达 80.0%/)).toBeInTheDocument();
  });

  it('triggers onRefresh when clicking refresh button', async () => {
    const handleRefresh = vi.fn().mockResolvedValue(undefined);
    render(<InfraQuotaCockpit data={mockQuotaData} onRefresh={handleRefresh} />);

    const refreshBtn = screen.getByTestId('refresh-quota-btn');
    await act(async () => {
      fireEvent.click(refreshBtn);
    });

    expect(handleRefresh).toHaveBeenCalledTimes(1);
  });

  it('simulates pre-flight quota check with approved result', async () => {
    const handleCheck = vi.fn().mockResolvedValue({
      allowed: true,
    });

    render(<InfraQuotaCockpit data={mockQuotaData} onCheckQuota={handleCheck} />);

    const checkBtn = screen.getByTestId('simulate-check-btn');
    await act(async () => {
      fireEvent.click(checkBtn);
    });

    expect(handleCheck).toHaveBeenCalledWith('active_agents', 1);

    const resultBox = screen.getByTestId('check-result-box');
    expect(resultBox).toBeInTheDocument();
    expect(screen.getByText(/准入核准通过：余量充足/)).toBeInTheDocument();
  });

  it('simulates pre-flight quota check with Fail-Closed rejection and remediation steps', async () => {
    const handleCheck = vi.fn().mockResolvedValue({
      allowed: false,
      rejectionReason: '持久 Volume 存储超限，不可分配',
      remediationSteps: ['清理历史构建缓存', '扩容组织持久卷配额'],
    });

    render(<InfraQuotaCockpit data={mockQuotaData} onCheckQuota={handleCheck} />);

    const checkBtn = screen.getByTestId('simulate-check-btn');
    await act(async () => {
      fireEvent.click(checkBtn);
    });

    const resultBox = screen.getByTestId('check-result-box');
    expect(resultBox).toBeInTheDocument();
    expect(screen.getByText(/Fail-Closed 拦截：资源超限/)).toBeInTheDocument();
    expect(screen.getByText('持久 Volume 存储超限，不可分配')).toBeInTheDocument();
    expect(screen.getByText('• 清理历史构建缓存')).toBeInTheDocument();
    expect(screen.getByText('• 扩容组织持久卷配额')).toBeInTheDocument();
  });
});
