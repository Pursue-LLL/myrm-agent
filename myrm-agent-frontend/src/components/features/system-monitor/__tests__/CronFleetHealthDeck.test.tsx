import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CronFleetHealthDeck } from '../CronFleetHealthDeck';
import { CronDoctorReportDrawer } from '../CronDoctorReportDrawer';
import type { CronFleetDoctorReport, QuickFixResponse } from '../cronDoctorTypes';

describe('CronFleetHealthDeck & CronDoctorReportDrawer', () => {
  const mockHealthyReport: CronFleetDoctorReport = {
    total_jobs: 5,
    healthy_jobs_count: 5,
    issues_count: 0,
    is_fleet_healthy: true,
    issues: [],
    inspected_at: '2026-10-12T12:00:00Z',
  };

  const mockIssuesReport: CronFleetDoctorReport = {
    total_jobs: 5,
    healthy_jobs_count: 3,
    issues_count: 2,
    is_fleet_healthy: false,
    issues: [
      {
        job_id: 'cron-report-03',
        job_name: '晨间行业简报投递',
        category: 'EXECUTION_FAILED',
        severity: 'critical',
        message: '上次运行抛出未捕获异常: HTTP 504 Gateway Timeout',
        suggested_fix: '检查上游接口网络，并配置指数退避重试',
      },
      {
        job_id: 'cron-stock-02',
        job_name: '多渠道库存同步',
        category: 'DELIVERY_UNVERIFIED',
        severity: 'warning',
        message: '投递完成但未收到 webhook 确认回执',
        suggested_fix: '核对接收方 webhook endpoint 配置或重试',
      },
    ],
    inspected_at: '2026-10-12T12:05:00Z',
  };

  it('renders healthy fleet deck with zero issues and emerald badge', () => {
    render(<CronFleetHealthDeck report={mockHealthyReport} />);

    expect(screen.getByTestId('cron-fleet-health-deck')).toBeInTheDocument();
    expect(screen.getByText('健康良好 · 零故障隐患')).toBeInTheDocument();
    expect(screen.getByText(/5 个自动化定时任务全部健康/)).toBeInTheDocument();
    expect(screen.queryByTestId('issues-summary-strip')).not.toBeInTheDocument();
  });

  it('renders degraded fleet deck with issue alert and preview strip', () => {
    render(<CronFleetHealthDeck report={mockIssuesReport} />);

    expect(screen.getByText('存在 2 处静默隐患待处理')).toBeInTheDocument();
    expect(screen.getByText(/1 项致命异常/)).toBeInTheDocument();
    expect(screen.getByTestId('issues-summary-strip')).toBeInTheDocument();
    expect(screen.getByText(/晨间行业简报投递/)).toBeInTheDocument();
  });

  it('triggers onScan and onOpenReport callbacks', () => {
    const handleScan = vi.fn();
    const handleOpen = vi.fn();

    render(
      <CronFleetHealthDeck
        report={mockIssuesReport}
        onScan={handleScan}
        onOpenReport={handleOpen}
      />
    );

    fireEvent.click(screen.getByTestId('scan-btn'));
    expect(handleScan).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('inspect-btn'));
    expect(handleOpen).toHaveBeenCalledTimes(1);
  });

  it('renders loading placeholder when report is null', () => {
    const handleScan = vi.fn();
    render(<CronFleetHealthDeck report={null} onScan={handleScan} />);

    expect(screen.getByTestId('cron-fleet-health-loading')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('scan-btn-initial'));
    expect(handleScan).toHaveBeenCalledTimes(1);
  });

  it('renders CronDoctorReportDrawer with healthy banner when fleet is healthy', () => {
    const handleClose = vi.fn();
    render(
      <CronDoctorReportDrawer
        isOpen={true}
        report={mockHealthyReport}
        onClose={handleClose}
      />
    );

    expect(screen.getByTestId('cron-doctor-drawer')).toBeInTheDocument();
    expect(screen.getByTestId('all-healthy-banner')).toBeInTheDocument();
    expect(screen.getByText('舰队防御门禁全部通过，零静默失效隐患')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('close-drawer-btn'));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('renders issue cards in drawer and triggers quick fix successfully', async () => {
    const handleClose = vi.fn();
    const handleQuickFix = vi.fn().mockResolvedValue({
      job_id: 'cron-report-03',
      fixed_category: 'EXECUTION_FAILED',
      status: 'REMEDIATED',
      message: '已清除上次致命异常标记并下发沙箱预检',
      remediated_at: '2026-10-12T12:06:00Z',
    } satisfies QuickFixResponse);

    render(
      <CronDoctorReportDrawer
        isOpen={true}
        report={mockIssuesReport}
        onClose={handleClose}
        onQuickFix={handleQuickFix}
      />
    );

    expect(screen.getByTestId('issues-list')).toBeInTheDocument();
    expect(screen.getAllByTestId('drawer-issue-item')).toHaveLength(2);
    expect(screen.getByText('执行崩溃')).toBeInTheDocument();
    expect(screen.getByText('回执未验真')).toBeInTheDocument();

    const fixBtn = screen.getByTestId('quick-fix-btn-cron-report-03');
    fireEvent.click(fixBtn);

    expect(handleQuickFix).toHaveBeenCalledWith('cron-report-03', 'EXECUTION_FAILED');

    await waitFor(() => {
      expect(screen.getByTestId('fix-feedback-cron-report-03')).toHaveTextContent(
        '已清除上次致命异常标记并下发沙箱预检'
      );
    });
  });

  it('does not render drawer when isOpen is false', () => {
    render(
      <CronDoctorReportDrawer
        isOpen={false}
        report={mockIssuesReport}
        onClose={vi.fn()}
      />
    );

    expect(screen.queryByTestId('cron-doctor-drawer')).not.toBeInTheDocument();
  });
});
