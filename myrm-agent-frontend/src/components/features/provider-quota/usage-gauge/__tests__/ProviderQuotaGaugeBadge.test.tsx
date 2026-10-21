import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProviderQuotaGaugeBadge } from '../ProviderQuotaGaugeBadge';
import { useProviderQuotaStore } from '../useProviderQuotaStore';

describe('ProviderQuotaGaugeBadge', () => {
  beforeEach(() => {
    useProviderQuotaStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('正确渲染初始提供商名称、百分比与余额', () => {
    render(<ProviderQuotaGaugeBadge />);

    expect(
      screen.getByTestId('provider-quota-gauge-root')
    ).toBeInTheDocument();
    expect(screen.getByTestId('quota-status-indicator')).toBeInTheDocument();
    expect(screen.getByTestId('provider-dropdown-toggle')).toHaveTextContent(
      'Nous Portal (GPT-6 Astra)'
    );
    expect(screen.getByTestId('quota-percentage-text')).toHaveTextContent(
      '76.4%'
    );
    expect(screen.getByTestId('quota-balance-usd')).toHaveTextContent('$18.50');
  });

  it('点击切换下拉按钮能够展开提供商列表并支持切换', () => {
    render(<ProviderQuotaGaugeBadge />);

    const toggleBtn = screen.getByTestId('provider-dropdown-toggle');
    fireEvent.click(toggleBtn);

    expect(
      screen.getByTestId('provider-dropdown-menu')
    ).toBeInTheDocument();
    expect(screen.getByTestId('provider-option-deepseek')).toBeInTheDocument();

    // 点击切换至 deepseek
    fireEvent.click(screen.getByTestId('provider-option-deepseek'));

    expect(useProviderQuotaStore.getState().activeProviderId).toBe('deepseek');
    expect(screen.getByTestId('provider-dropdown-toggle')).toHaveTextContent(
      'DeepSeek Platform'
    );
    expect(screen.getByTestId('quota-percentage-text')).toHaveTextContent(
      '96%'
    );
  });

  it('点击进度条区域能够呼出全景分析大盘弹窗', () => {
    render(<ProviderQuotaGaugeBadge />);

    const openAnalyticsBtn = screen.getByTestId('open-analytics-btn');
    fireEvent.click(openAnalyticsBtn);

    expect(useProviderQuotaStore.getState().isAnalyticsModalOpen).toBe(true);
  });
});
