import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { SkillStarterWizardCard } from '../SkillStarterWizardCard';
import { useSkillStarterWizardStore } from '../useSkillStarterWizardStore';

describe('SkillStarterWizardCard', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useSkillStarterWizardStore.getState().resetWizardState();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when closed', () => {
    const { container } = render(<SkillStarterWizardCard />);
    expect(container.firstChild).toBeNull();
  });

  it('renders full wizard card when opened with preset', () => {
    act(() => {
      useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    });

    render(<SkillStarterWizardCard />);

    expect(screen.getByRole('region', { name: '技能安装后即刻体验向导卡' })).toBeInTheDocument();
    expect(screen.getByText('微信群聊晨报生成器')).toBeInTheDocument();
    expect(screen.getByText('办公协作与社群运营')).toBeInTheDocument();
    expect(screen.getByText('安装就绪')).toBeInTheDocument();
    expect(screen.getByText('受控本地嗅探')).toBeInTheDocument();
    expect(screen.getByText('场景精炼参数配置')).toBeInTheDocument();
    expect(screen.getByText('即刻单填试跑')).toBeInTheDocument();
    expect(screen.getByText('开启 每天早上 08:00 自动生成')).toBeInTheDocument();
  });

  it('allows changing sniffed resource and parameter perspective', () => {
    act(() => {
      useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    });

    render(<SkillStarterWizardCard />);

    const select = screen.getByLabelText('目标群聊');
    fireEvent.change(select, { target: { value: 'wx_grp_fullstack_dev' } });

    expect(useSkillStarterWizardStore.getState().selectedResourceId).toBe('wx_grp_fullstack_dev');

    // Click on perspective button
    const salesLeadButton = screen.getByRole('button', { name: /销售线索/i });
    fireEvent.click(salesLeadButton);

    expect(useSkillStarterWizardStore.getState().formValues.business_perspective).toBe('sales_leads');
  });

  it('handles trial run execution flow', async () => {
    act(() => {
      useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    });

    render(<SkillStarterWizardCard />);

    const trialRunButton = screen.getByRole('button', { name: '立即试跑一次' });
    fireEvent.click(trialRunButton);

    // Fast-forward timers for trial run execution
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(screen.getByText('试跑成功，产物已就绪')).toBeInTheDocument();
    expect(screen.getByText(/提炼要素: 142 条/i)).toBeInTheDocument();
  });

  it('handles 1-click routine hosting toggle', async () => {
    act(() => {
      useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    });

    render(<SkillStarterWizardCard />);

    const switchButton = screen.getByRole('switch', { name: '一键开启或关闭后台定时托管' });
    expect(switchButton).toHaveAttribute('aria-checked', 'false');

    await act(async () => {
      fireEvent.click(switchButton);
    });

    expect(switchButton).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('后台静默托管中')).toBeInTheDocument();
    expect(screen.getByText(/推送接收渠道:/i)).toBeInTheDocument();

    // Toggle channel
    const notifChannelButton = screen.getByRole('button', { name: /系统通知/i });
    fireEvent.click(notifChannelButton);
    expect(useSkillStarterWizardStore.getState().cronBlueprint.targetChannel).toBe('desktop_notification');
  });

  it('closes wizard when close button is clicked', () => {
    act(() => {
      useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    });

    render(<SkillStarterWizardCard />);

    const closeButton = screen.getByRole('button', { name: '关闭向导卡' });
    fireEvent.click(closeButton);

    expect(useSkillStarterWizardStore.getState().isOpen).toBe(false);
  });
});
