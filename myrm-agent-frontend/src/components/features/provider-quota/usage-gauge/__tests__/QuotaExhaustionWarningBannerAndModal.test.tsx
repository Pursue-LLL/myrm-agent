import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuotaExhaustionWarningBanner } from '../QuotaExhaustionWarningBanner';
import { ProviderQuotaAnalyticsModal } from '../ProviderQuotaAnalyticsModal';
import { useProviderQuotaStore } from '../useProviderQuotaStore';

describe('QuotaExhaustionWarningBanner & ProviderQuotaAnalyticsModal', () => {
  beforeEach(() => {
    useProviderQuotaStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('未开启告警时不渲染 QuotaExhaustionWarningBanner', () => {
    const { container } = render(<QuotaExhaustionWarningBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('开启告警时正确渲染预警横幅并支持一键自愈故障转移', () => {
    // 激活危急渠道 openrouter
    useProviderQuotaStore.getState().setActiveProvider('openrouter');

    render(<QuotaExhaustionWarningBanner />);

    expect(
      screen.getByTestId('quota-exhaustion-warning-banner')
    ).toBeInTheDocument();
    expect(screen.getByText('算力配额濒临枯竭预警')).toBeInTheDocument();
    expect(screen.getByText('剩余 3%')).toBeInTheDocument();

    // 点击一键自愈热切换
    const failoverBtn = screen.getByTestId('failover-action-btn');
    fireEvent.click(failoverBtn);

    // 默认备用渠道被切换（nous 或其他健康渠道）
    expect(useProviderQuotaStore.getState().isExhaustionWarningOpen).toBe(false);
    expect(useProviderQuotaStore.getState().lastFailoverAction).toBeDefined();
  });

  it('点击关闭告警按钮能够收起横幅', () => {
    useProviderQuotaStore.getState().setExhaustionWarningOpen(true);
    render(<QuotaExhaustionWarningBanner />);

    const dismissBtn = screen.getByTestId('dismiss-warning-btn');
    fireEvent.click(dismissBtn);

    expect(useProviderQuotaStore.getState().isExhaustionWarningOpen).toBe(false);
  });

  it('未开启弹窗时不渲染 ProviderQuotaAnalyticsModal', () => {
    const { container } = render(<ProviderQuotaAnalyticsModal />);
    expect(container.firstChild).toBeNull();
  });

  it('开启弹窗时渲染四个维度指标卡、模型占比条与导出按钮', () => {
    useProviderQuotaStore.getState().setAnalyticsModalOpen(true);

    // 模拟 URL.createObjectURL 和 revokeObjectURL 供 CSV 导出
    const mockCreateObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    const mockRevokeObjectURL = vi.fn();
    globalThis.URL.createObjectURL = mockCreateObjectURL;
    globalThis.URL.revokeObjectURL = mockRevokeObjectURL;

    render(<ProviderQuotaAnalyticsModal />);

    expect(
      screen.getByTestId('provider-quota-analytics-modal-content')
    ).toBeInTheDocument();
    expect(screen.getByTestId('analytics-balance-usd')).toHaveTextContent(
      '$18.50'
    );
    expect(screen.getByTestId('analytics-percentage')).toHaveTextContent(
      '76.4%'
    );
    expect(screen.getByTestId('analytics-burn-rate')).toHaveTextContent(
      '$1.25/天'
    );
    expect(screen.getByTestId('analytics-remaining-days')).toHaveTextContent(
      '14.8 天'
    );

    // 导出 CSV
    const exportBtn = screen.getByTestId('export-csv-btn');
    fireEvent.click(exportBtn);
    expect(mockCreateObjectURL).toHaveBeenCalled();

    // 关闭弹窗
    const closeBtn = screen.getByTestId('close-analytics-modal-btn');
    fireEvent.click(closeBtn);
    expect(useProviderQuotaStore.getState().isAnalyticsModalOpen).toBe(false);
  });

  it('按下 Escape 键能够关闭 ProviderQuotaAnalyticsModal', () => {
    useProviderQuotaStore.getState().setAnalyticsModalOpen(true);
    render(<ProviderQuotaAnalyticsModal />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useProviderQuotaStore.getState().isAnalyticsModalOpen).toBe(false);
  });
});
