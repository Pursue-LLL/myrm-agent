import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HostFingerprintBadge } from '../HostFingerprintBadge';
import { HostDevice } from '../fingerprintStudioTypes';
import { useFingerprintStudioStore } from '../useFingerprintStudioStore';

describe('HostFingerprintBadge Component', () => {
  const mockMacDevice: HostDevice = {
    hardware: {
      deviceId: 'host_mac_m3',
      hostName: 'MacBook Pro 16"',
      platform: 'macos',
      architecture: 'apple_silicon',
      chipModel: 'Apple M3 Max',
      kind: 'local_laptop',
      isCurrentHost: true,
    },
    telemetry: {
      cpuUsagePct: 25,
      memoryUsagePct: 40,
      gpuUsagePct: 15,
      activeTasksCount: 1,
      lastHeartbeatMs: Date.now(),
      latencyMs: 2,
    },
    status: 'busy',
  };

  const mockWinDevice: HostDevice = {
    hardware: {
      deviceId: 'host_win_rtx',
      hostName: 'Workstation Rig',
      platform: 'windows',
      architecture: 'amd_x64',
      chipModel: 'Ryzen 9 7950X',
      gpuModel: 'NVIDIA RTX 4090 24GB',
      kind: 'local_workstation',
      isCurrentHost: false,
    },
    telemetry: {
      cpuUsagePct: 10,
      memoryUsagePct: 30,
      gpuUsagePct: 5,
      activeTasksCount: 0,
      lastHeartbeatMs: Date.now(),
      latencyMs: 12,
    },
    status: 'online',
  };

  beforeEach(() => {
    useFingerprintStudioStore.getState().resetAll();
  });

  it('renders mini badge correctly for macbook device', () => {
    render(<HostFingerprintBadge device={mockMacDevice} mode="mini" />);
    expect(screen.getByText('MacBook Pro 16"')).toBeDefined();
    expect(screen.getByText('Apple')).toBeDefined();
  });

  it('renders GPU tag when device has dedicated GPU', () => {
    render(<HostFingerprintBadge device={mockWinDevice} mode="mini" />);
    expect(screen.getByText('Workstation Rig')).toBeDefined();
    expect(screen.getByText('RTX')).toBeDefined();
  });

  it('renders expanded mode with load score', () => {
    render(<HostFingerprintBadge device={mockMacDevice} mode="expanded" />);
    expect(screen.getByText(/负荷/)).toBeDefined();
  });

  it('displays detailed popover on hover and allows switching active device', () => {
    render(
      <HostFingerprintBadge
        device={mockWinDevice}
        mode="mini"
        showSwitchAction={true}
      />
    );

    const badgeContainer = screen.getByText('Workstation Rig').closest('div');
    expect(badgeContainer).toBeDefined();

    // 触发悬停
    if (badgeContainer?.parentElement) {
      fireEvent.mouseEnter(badgeContainer.parentElement);
    }

    // 悬停后应出现 Popover
    expect(screen.getByText('Workstation Rig [WINDOWS]')).toBeDefined();
    expect(screen.getByText('CPU 负载')).toBeDefined();
    expect(screen.getByText('10%')).toBeDefined();
    expect(screen.getByText('12 ms')).toBeDefined();

    // 点击设为默认调度主机
    const switchButton = screen.getByRole('button', { name: /设为默认调度主机/ });
    fireEvent.click(switchButton);

    expect(useFingerprintStudioStore.getState().activeDeviceId).toBe('host_win_rtx');
  });
});
