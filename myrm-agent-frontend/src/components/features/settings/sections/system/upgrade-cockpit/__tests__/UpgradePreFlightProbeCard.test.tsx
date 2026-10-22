import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { UpgradePreFlightProbeCard } from '../UpgradePreFlightProbeCard';
import { ActiveTaskDrainSafetyBanner } from '../ActiveTaskDrainSafetyBanner';
import type {
  ActiveTaskDrainSafetyCheck,
  NetworkMirrorProbeResult,
} from '../upgradeCockpitTypes';

const mockProbes: NetworkMirrorProbeResult[] = [
  {
    id: 'cnb',
    name: 'CNB 国内高速镜像',
    endpointUrl: 'https://cnb.cool/mirrors/myrm-agent',
    latencyMs: 25,
    status: 'optimal',
    isRecommended: true,
    statusDescription: '极速低延迟',
  },
  {
    id: 'github',
    name: 'GitHub 官方源',
    endpointUrl: 'https://github.com/Pursue-LLL/myrm-agent',
    latencyMs: 420,
    status: 'degraded',
    isRecommended: false,
    statusDescription: '延迟较高',
  },
];

describe('UpgradePreFlightProbeCard', () => {
  it('renders probe card with title, mirrors, and recommended badge', () => {
    const onSelectMirror = vi.fn();
    const onRefreshProbes = vi.fn();

    render(
      <UpgradePreFlightProbeCard
        probes={mockProbes}
        selectedMirrorId="cnb"
        onSelectMirror={onSelectMirror}
        onRefreshProbes={onRefreshProbes}
        isProbing={false}
      />,
    );

    expect(screen.getByText('前置网络诊断探针')).toBeInTheDocument();
    expect(screen.getByText('CNB 国内高速镜像')).toBeInTheDocument();
    expect(screen.getByText('GitHub 官方源')).toBeInTheDocument();
    expect(screen.getByText('推荐')).toBeInTheDocument();
    expect(screen.getByText('25ms')).toBeInTheDocument();
  });

  it('handles selecting mirror and clicking refresh probes', () => {
    const onSelectMirror = vi.fn();
    const onRefreshProbes = vi.fn();

    render(
      <UpgradePreFlightProbeCard
        probes={mockProbes}
        selectedMirrorId="cnb"
        onSelectMirror={onSelectMirror}
        onRefreshProbes={onRefreshProbes}
        isProbing={false}
      />,
    );

    // Select github mirror
    fireEvent.click(screen.getByTestId('mirror-probe-item-github'));
    expect(onSelectMirror).toHaveBeenCalledWith('github');

    // Click refresh
    fireEvent.click(screen.getByTestId('refresh-probes-btn'));
    expect(onRefreshProbes).toHaveBeenCalled();
  });

  it('disables refresh button when isProbing is true', () => {
    render(
      <UpgradePreFlightProbeCard
        probes={mockProbes}
        selectedMirrorId="cnb"
        onSelectMirror={vi.fn()}
        onRefreshProbes={vi.fn()}
        isProbing={true}
      />,
    );

    const btn = screen.getByTestId('refresh-probes-btn');
    expect(btn).toBeDisabled();
    expect(screen.getByText('正在体检...')).toBeInTheDocument();
  });
});

describe('ActiveTaskDrainSafetyBanner', () => {
  it('renders safe banner when no active tasks exist', () => {
    const safeCheck: ActiveTaskDrainSafetyCheck = {
      hasActiveGoal: false,
      hasActiveCron: false,
      activeTaskCount: 0,
      activeTasks: [],
      recommendation: 'safe_to_reload',
      recommendationRationale: '当前系统空闲，可立即升级',
    };

    render(<ActiveTaskDrainSafetyBanner safetyCheck={safeCheck} />);

    expect(screen.getByTestId('task-safety-banner-safe')).toBeInTheDocument();
    expect(screen.getByText('当前系统空闲，可立即升级')).toBeInTheDocument();
  });

  it('renders active task warning with strategy options and triggers callback', () => {
    const onSelectStrategy = vi.fn();
    const busyCheck: ActiveTaskDrainSafetyCheck = {
      hasActiveGoal: true,
      hasActiveCron: false,
      activeTaskCount: 1,
      activeTasks: [
        {
          id: 'goal-01',
          type: 'goal',
          title: '全自动行业研报深度分析',
          progressPercent: 85,
        },
      ],
      recommendation: 'drain_first',
      recommendationRationale: '当前有 1 个任务正在执行中，建议排空后再重载',
    };

    render(
      <ActiveTaskDrainSafetyBanner
        safetyCheck={busyCheck}
        onSelectStrategy={onSelectStrategy}
      />,
    );

    expect(screen.getByTestId('task-safety-banner-active-tasks')).toBeInTheDocument();
    expect(screen.getByText('全自动行业研报深度分析')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();

    // Trigger drain first strategy
    fireEvent.click(screen.getByTestId('drain-first-strategy-btn'));
    expect(onSelectStrategy).toHaveBeenCalledWith('drain_first');

    // Trigger checkpoint upgrade strategy
    fireEvent.click(screen.getByTestId('checkpoint-upgrade-strategy-btn'));
    expect(onSelectStrategy).toHaveBeenCalledWith('checkpoint_and_upgrade');
  });
});
