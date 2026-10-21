import React from 'react';
import { render, screen, fireEvent, act, within } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { MultiPaneFlexibleCockpit } from '../MultiPaneFlexibleCockpit';
import { useMultiPaneCockpitStore } from '../useMultiPaneCockpitStore';

describe('MultiPaneFlexibleCockpit', () => {
  beforeEach(() => {
    act(() => {
      useMultiPaneCockpitStore.getState().resetCockpitState();
    });
  });

  it('renders multi-pane flexible cockpit layout with default elements', () => {
    render(<MultiPaneFlexibleCockpit />);

    expect(screen.getByLabelText('多栏自由桌面协同驾驶舱')).toBeInTheDocument();
    expect(screen.getByText('智能体多栏协同视界')).toBeInTheDocument();
    const roster = screen.getByLabelText('智能体团队名册');
    expect(roster).toBeInTheDocument();
    expect(screen.getByLabelText('Bot 定时任务监控面板')).toBeInTheDocument();

    // Verify bots rendered in roster
    expect(within(roster).getByText('晨报速递管家')).toBeInTheDocument();
    expect(within(roster).getByText('深度研报学者')).toBeInTheDocument();
    expect(within(roster).getByText('代码安全守卫')).toBeInTheDocument();
  });

  it('switches selected bot and updates main viewport', () => {
    render(<MultiPaneFlexibleCockpit />);

    const researcherButton = screen.getByRole('button', { name: /深度研报学者/i });
    fireEvent.click(researcherButton);

    expect(useMultiPaneCockpitStore.getState().selectedBotId).toBe('bot_deep_researcher');
    // Main header displays updated bot name
    expect(screen.getByRole('heading', { level: 2, name: '深度研报学者' })).toBeInTheDocument();
  });

  it('triggers handoff when clicking shuttle button on active bot', () => {
    render(<MultiPaneFlexibleCockpit />);

    // Click on handoff shuttle button for deep researcher
    const handoffButtons = screen.getAllByTitle('穿梭直达任务现场');
    expect(handoffButtons.length).toBeGreaterThan(0);
    fireEvent.click(handoffButtons[0]);

    expect(screen.getByText(/已秒级穿梭至「晨报速递管家」执行现场/i)).toBeInTheDocument();
    expect(screen.getByText('实时推流中')).toBeInTheDocument();
  });

  it('switches between 2-pane, 3-pane, and 4-pane layouts', () => {
    render(<MultiPaneFlexibleCockpit />);

    // Switch to 4-pane
    const fourPaneButton = screen.getByRole('button', { name: /4 栏/i });
    fireEvent.click(fourPaneButton);

    expect(useMultiPaneCockpitStore.getState().paneMode).toBe('four_pane');
    expect(screen.getByLabelText('工件实时预览面板')).toBeInTheDocument();

    // Switch to 2-pane
    const twoPaneButton = screen.getByRole('button', { name: /2 栏/i });
    fireEvent.click(twoPaneButton);

    expect(useMultiPaneCockpitStore.getState().paneMode).toBe('two_pane');
    expect(screen.queryByLabelText('Bot 定时任务监控面板')).not.toBeInTheDocument();
  });

  it('toggles bot cron job switch', () => {
    render(<MultiPaneFlexibleCockpit />);

    const cronSwitch = screen.getByRole('switch', { name: /每日早上 08:00 群聊晨报/i });
    expect(cronSwitch).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(cronSwitch);
    expect(cronSwitch).toHaveAttribute('aria-checked', 'false');
  });

  it('collapses and expands bot roster', () => {
    render(<MultiPaneFlexibleCockpit />);

    const collapseButton = screen.getByRole('button', { name: '收起名册' });
    fireEvent.click(collapseButton);

    expect(useMultiPaneCockpitStore.getState().isRosterCollapsed).toBe(true);
    expect(screen.getByRole('button', { name: '展开名册' })).toBeInTheDocument();
  });
});
