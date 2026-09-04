/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { WeChatRiskDisclosureBanner } from '../WeChatRiskDisclosureBanner';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('WeChatRiskDisclosureBanner', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('renders full banner with risk warning by default', () => {
    render(<WeChatRiskDisclosureBanner />);
    expect(screen.getByTestId('wechat-risk-banner-full')).toBeInTheDocument();
    expect(screen.getByText('wechatRiskBannerTitle')).toBeInTheDocument();
    expect(screen.getByText('wechatRiskBannerDesc')).toBeInTheDocument();
    expect(screen.getByText('wechatRiskBannerWeComHint')).toBeInTheDocument();
  });

  it('collapses into compact bar when dismiss is clicked and persists to localStorage', () => {
    render(<WeChatRiskDisclosureBanner />);
    const dismissBtns = screen.getAllByRole('button', { name: 'wechatRiskBannerDismiss' });
    fireEvent.click(dismissBtns[0]);

    expect(screen.queryByTestId('wechat-risk-banner-full')).not.toBeInTheDocument();
    expect(screen.getByTestId('wechat-risk-banner-compact')).toBeInTheDocument();
    expect(screen.getByText('wechatRiskBannerCompactTitle')).toBeInTheDocument();
    expect(localStorage.getItem('myrm_wechat_risk_banner_dismissed')).toBe('1');
  });

  it('expands back to full banner when compact expand button is clicked', () => {
    localStorage.setItem('myrm_wechat_risk_banner_dismissed', '1');
    render(<WeChatRiskDisclosureBanner />);

    expect(screen.getByTestId('wechat-risk-banner-compact')).toBeInTheDocument();
    const expandBtn = screen.getByRole('button', { name: /wechatRiskBannerExpand/i });
    fireEvent.click(expandBtn);

    expect(screen.getByTestId('wechat-risk-banner-full')).toBeInTheDocument();
    expect(localStorage.getItem('myrm_wechat_risk_banner_dismissed')).toBeNull();
  });

  it('renders WeCom action button and invokes callback when onNavigateToWeCom is passed', () => {
    const onNavigate = vi.fn();
    render(<WeChatRiskDisclosureBanner onNavigateToWeCom={onNavigate} />);

    const wecomBtn = screen.getByRole('button', { name: /wechatRiskBannerWeComAction/i });
    expect(wecomBtn).toBeInTheDocument();

    fireEvent.click(wecomBtn);
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
