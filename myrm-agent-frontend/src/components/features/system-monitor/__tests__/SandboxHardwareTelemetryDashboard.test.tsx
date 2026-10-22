import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SandboxHardwareTelemetryDashboard } from '../SandboxHardwareTelemetryDashboard';
import { HardwareTelemetrySnapshotData } from '../sandboxHardwareTelemetryTypes';

describe('SandboxHardwareTelemetryDashboard Component', () => {
  const mockNormalSnapshot: HardwareTelemetrySnapshotData = {
    latest_sample: {
      cpu_percent: 28.5,
      memory_used_bytes: 4294967296,
      memory_total_bytes: 17179869184,
      memory_percent: 25.0,
      disk_used_bytes: 48318382080,
      disk_total_bytes: 107374182400,
      disk_percent: 45.0,
      network_bytes_sent: 1048576,
      network_bytes_recv: 2097152,
      timestamp_ms: 1718000000000,
    },
    current_level: 'normal',
    config: {
      warning_cpu_threshold: 80.0,
      suspend_cpu_threshold: 90.0,
      trip_cpu_threshold: 95.0,
      warning_mem_threshold: 80.0,
      suspend_mem_threshold: 90.0,
      trip_mem_threshold: 95.0,
      max_consecutive_violations: 3,
      max_task_duration_seconds: 600.0,
    },
    consecutive_violations: 0,
    incident_history: [],
    generated_at_ms: 1718000000000,
  };

  const mockTrippedSnapshot: HardwareTelemetrySnapshotData = {
    ...mockNormalSnapshot,
    current_level: 'tripped',
    consecutive_violations: 3,
    latest_sample: {
      ...mockNormalSnapshot.latest_sample!,
      cpu_percent: 98.5,
    },
    incident_history: [
      {
        level: 'tripped',
        triggered_metric: 'CPU',
        current_value: 98.5,
        threshold_value: 95.0,
        action_description: '硬熔断已触发: CPU 持续超标 (98.5% >= 95.0%), 已物理终止失控进程组',
        sample: {
          ...mockNormalSnapshot.latest_sample!,
          cpu_percent: 98.5,
        },
        evaluated_at_ms: 1718000005000,
      },
    ],
  };

  it('renders dashboard title, normal status banner and hardware metric cards', () => {
    render(<SandboxHardwareTelemetryDashboard snapshot={mockNormalSnapshot} />);

    expect(screen.getByText('沙箱硬件资源遥测与失控三级熔断控制台')).toBeInTheDocument();
    expect(screen.getByText('安界信 × Qoder 运维控制面对齐')).toBeInTheDocument();
    expect(screen.getByText('🟢 绿色安全放行 (NORMAL)')).toBeInTheDocument();
    expect(screen.getByText('28.5%')).toBeInTheDocument();
    expect(screen.getByText('25.0%')).toBeInTheDocument();
    expect(screen.getByText('45.0%')).toBeInTheDocument();
    expect(screen.getByText('暂无违规事故，沙箱运行平稳')).toBeInTheDocument();
  });

  it('renders tripped level banner and incident table', () => {
    render(<SandboxHardwareTelemetryDashboard snapshot={mockTrippedSnapshot} />);

    expect(screen.getByText('🔴 红色硬熔断已触发 (TRIPPED)')).toBeInTheDocument();
    expect(screen.getByText('98.5%')).toBeInTheDocument();

    const tripBadges = screen.getAllByText('TRIPPED');
    expect(tripBadges.length).toBeGreaterThanOrEqual(1);

    expect(screen.getByText('硬熔断已触发: CPU 持续超标 (98.5% >= 95.0%), 已物理终止失控进程组')).toBeInTheDocument();
  });

  it('handles reset breaker and threshold configuration callbacks', async () => {
    const handleReset = vi.fn();
    const handleUpdate = vi.fn();

    render(
      <SandboxHardwareTelemetryDashboard
        snapshot={mockNormalSnapshot}
        onResetBreaker={handleReset}
        onUpdateThresholds={handleUpdate}
      />
    );

    const resetBtn = screen.getByRole('button', { name: '复位恢复熔断' });
    await React.act(async () => {
      fireEvent.click(resetBtn);
    });
    expect(handleReset).toHaveBeenCalledTimes(1);

    const applyBtn = screen.getByRole('button', { name: '应用新阈值' });
    await React.act(async () => {
      fireEvent.click(applyBtn);
    });
    expect(handleUpdate).toHaveBeenCalledTimes(1);
  });
});
