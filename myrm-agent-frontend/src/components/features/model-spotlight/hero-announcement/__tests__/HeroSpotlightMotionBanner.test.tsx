import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { HeroSpotlightMotionBanner, getBadgeLabel } from '../HeroSpotlightMotionBanner';
import { useModelSpotlightStore } from '../useModelSpotlightStore';
import { SPOTLIGHT_CATALOG } from '../spotlightCatalogData';

describe('HeroSpotlightMotionBanner Component', () => {
  beforeEach(() => {
    act(() => {
      useModelSpotlightStore.getState().restoreDismissedSpotlights();
      useModelSpotlightStore.getState().closePlayground();
      useModelSpotlightStore.getState().closeMountModal();
    });
  });

  it('renders badge labels correctly', () => {
    expect(getBadgeLabel('flagship')).toBe('旗舰突破');
    expect(getBadgeLabel('discount')).toBe('限时特惠');
    expect(getBadgeLabel('reasoning')).toBe('深度推理');
    expect(getBadgeLabel('open-weights')).toBe('开源权重');
    expect(getBadgeLabel('multimodal')).toBe('全模态');
    expect(getBadgeLabel('ultra-fast')).toBe('极速低延迟');
  });

  it('renders expanded banner with active spotlight model details', () => {
    render(<HeroSpotlightMotionBanner />);

    expect(screen.getByTestId('spotlight-banner-expanded')).toBeInTheDocument();
    expect(screen.getByText('GPT-6 Astra')).toBeInTheDocument();
    expect(screen.getByText('OpenAI')).toBeInTheDocument();
    expect(screen.getByText(/次世代超大规模多模态推理旗舰/)).toBeInTheDocument();
    expect(screen.getByText('前沿聚光灯')).toBeInTheDocument();
    expect(screen.getByText('限时减免 20%')).toBeInTheDocument();
    expect(screen.getByText(/上下文：1M/)).toBeInTheDocument();
  });

  it('switches active model when clicking tabs in the banner', () => {
    render(<HeroSpotlightMotionBanner />);

    const claudeTab = screen.getByRole('tab', { name: 'Claude' });
    fireEvent.click(claudeTab);

    expect(useModelSpotlightStore.getState().activeSpotlightId).toBe(
      'spotlight-claude-3-7-sonnet'
    );
    expect(screen.getByText(/Claude 3.7 Sonnet/)).toBeInTheDocument();
  });

  it('toggles between expanded and collapsed banner views', () => {
    render(<HeroSpotlightMotionBanner />);

    const collapseButton = screen.getByRole('button', { name: '折叠聚光灯横幅' });
    fireEvent.click(collapseButton);

    expect(screen.getByTestId('spotlight-banner-collapsed')).toBeInTheDocument();
    expect(screen.getByText(/前沿上新：GPT-6 Astra/)).toBeInTheDocument();

    const expandButton = screen.getByRole('button', { name: '展开聚光灯横幅' });
    fireEvent.click(expandButton);

    expect(screen.getByTestId('spotlight-banner-expanded')).toBeInTheDocument();
  });

  it('triggers playground modal on "立即试用" button click', () => {
    render(<HeroSpotlightMotionBanner />);

    const tryButton = screen.getByRole('button', { name: '一键热试用临时沙箱' });
    fireEvent.click(tryButton);

    expect(useModelSpotlightStore.getState().isPlaygroundOpen).toBe(true);
    expect(useModelSpotlightStore.getState().playgroundSpotlight?.name).toBe('GPT-6 Astra');
  });

  it('triggers mount modal on "挂载至智能体" button click', () => {
    render(<HeroSpotlightMotionBanner />);

    const mountButton = screen.getByRole('button', { name: '一键热挂载至当前智能体' });
    fireEvent.click(mountButton);

    expect(useModelSpotlightStore.getState().isMountModalOpen).toBe(true);
    expect(useModelSpotlightStore.getState().mountTargetSpotlight?.name).toBe('GPT-6 Astra');
  });

  it('dismisses spotlight and hides banner when all items are dismissed', () => {
    const { unmount } = render(<HeroSpotlightMotionBanner />);

    // Dismiss first
    const closeBtn = screen.getByRole('button', { name: '关闭本条聚光灯公告' });
    fireEvent.click(closeBtn);

    // Active spotlight shifts to Claude
    expect(useModelSpotlightStore.getState().activeSpotlightId).toBe(
      SPOTLIGHT_CATALOG[1].id
    );

    unmount();

    // Dismiss remaining spotlights
    act(() => {
      useModelSpotlightStore.getState().dismissSpotlight(SPOTLIGHT_CATALOG[1].id, true);
      useModelSpotlightStore.getState().dismissSpotlight(SPOTLIGHT_CATALOG[2].id, true);
    });

    const { container } = render(<HeroSpotlightMotionBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('renders collapsed bar trial button correctly', () => {
    act(() => {
      useModelSpotlightStore.setState({ isBannerCollapsed: true });
    });
    render(<HeroSpotlightMotionBanner />);

    const trialBtn = screen.getByRole('button', { name: '一键热试用' });
    fireEvent.click(trialBtn);

    expect(useModelSpotlightStore.getState().isPlaygroundOpen).toBe(true);
  });
});
