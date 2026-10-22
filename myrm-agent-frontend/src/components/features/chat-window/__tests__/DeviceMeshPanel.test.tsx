'use client';

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  DeviceMeshPanel,
  MeshDeviceNodeItem,
} from '../DeviceMeshPanel';

const mockNodes: MeshDeviceNodeItem[] = [
  {
    nodeId: 'rpi-living-room',
    name: 'Living Room Pi 5',
    kind: 'raspberry_pi',
    ipOrHostname: '192.168.1.105',
    status: 'online',
    capabilities: ['camera', 'gpio'],
    telemetry: {
      cpuUsagePct: 15.4,
      memoryUsagePct: 42.1,
      uptimeSeconds: 86400,
      activeTasks: 1,
    },
  },
  {
    nodeId: 'mac-studio-m2',
    name: 'Compute Mac Studio',
    kind: 'mac_mini',
    ipOrHostname: '192.168.1.88',
    status: 'unpaired',
    capabilities: ['metal_acceleration'],
    telemetry: {
      cpuUsagePct: 5.0,
      memoryUsagePct: 20.0,
      uptimeSeconds: 12000,
      activeTasks: 0,
    },
  },
  {
    nodeId: 'gpu-server-01',
    name: 'RTX 4090 Workstation',
    kind: 'linux_server',
    ipOrHostname: '192.168.1.200',
    status: 'busy',
    capabilities: ['cuda', 'docker'],
    telemetry: {
      cpuUsagePct: 88.0,
      memoryUsagePct: 75.5,
      gpuUsagePct: 92.0,
      uptimeSeconds: 54000,
      activeTasks: 4,
    },
  },
];

describe('DeviceMeshPanel', () => {
  it('renders empty state when no nodes provided', () => {
    render(<DeviceMeshPanel nodes={[]} />);

    expect(screen.getByTestId('empty-mesh-state')).toBeInTheDocument();
    expect(screen.getByText('暂无连接的边缘设备')).toBeInTheDocument();
    expect(screen.getByText('(0 台设备)')).toBeInTheDocument();
  });

  it('renders device nodes list with telemetry and status badges', () => {
    render(<DeviceMeshPanel nodes={mockNodes} />);

    expect(screen.getByTestId('nodes-grid')).toBeInTheDocument();
    expect(screen.getByText('Living Room Pi 5')).toBeInTheDocument();
    expect(screen.getByText('Compute Mac Studio')).toBeInTheDocument();
    expect(screen.getByText('RTX 4090 Workstation')).toBeInTheDocument();

    // Check status counts in header
    expect(screen.getByText('在线 1')).toBeInTheDocument();
    expect(screen.getByText('忙碌 1')).toBeInTheDocument();
    expect(screen.getByText('待配对 1')).toBeInTheDocument();

    // Check telemetry numbers
    expect(screen.getByText('15.4%')).toBeInTheDocument();
    expect(screen.getByText('42.1%')).toBeInTheDocument();
    expect(screen.getByText('88.0%')).toBeInTheDocument();

    // Capabilities
    expect(screen.getByText('camera')).toBeInTheDocument();
    expect(screen.getByText('gpio')).toBeInTheDocument();
    expect(screen.getByText('metal_acceleration')).toBeInTheDocument();
  });

  it('triggers onRefresh when clicking refresh button', () => {
    const onRefresh = vi.fn();
    render(<DeviceMeshPanel nodes={mockNodes} onRefresh={onRefresh} />);

    const refreshBtn = screen.getByTestId('refresh-mesh-btn');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('handles node pairing flow', async () => {
    const onPairNode = vi.fn().mockResolvedValue(true);
    render(<DeviceMeshPanel nodes={mockNodes} onPairNode={onPairNode} />);

    const tokenInput = screen.getByTestId('pairing-token-input-mac-studio-m2');
    const pairBtn = screen.getByTestId('pair-node-btn-mac-studio-m2');

    // Initially disabled because token input is empty
    expect(pairBtn).toBeDisabled();

    // Enter token
    fireEvent.change(tokenInput, { target: { value: 'm2-secret-pass' } });
    expect(pairBtn).not.toBeDisabled();

    // Click pair
    fireEvent.click(pairBtn);

    await waitFor(() => {
      expect(onPairNode).toHaveBeenCalledWith('mac-studio-m2', 'm2-secret-pass');
    });
  });

  it('handles command dispatch flow and displays feedback', async () => {
    const onDispatchCommand = vi.fn().mockResolvedValue('Linux 6.1.0-rpi-arm64 OK');
    render(<DeviceMeshPanel nodes={mockNodes} onDispatchCommand={onDispatchCommand} />);

    const cmdInput = screen.getByTestId('command-input-rpi-living-room');
    const dispatchBtn = screen.getByTestId('dispatch-btn-rpi-living-room');

    expect(dispatchBtn).toBeDisabled();

    fireEvent.change(cmdInput, { target: { value: 'uname -a' } });
    expect(dispatchBtn).not.toBeDisabled();

    fireEvent.click(dispatchBtn);

    await waitFor(() => {
      expect(onDispatchCommand).toHaveBeenCalledWith('rpi-living-room', 'uname -a');
    });

    // Feedback should be displayed
    await waitFor(() => {
      expect(screen.getByText('Linux 6.1.0-rpi-arm64 OK')).toBeInTheDocument();
    });
  });

  it('triggers onRemoveNode when clicking trash icon', () => {
    const onRemoveNode = vi.fn();
    render(<DeviceMeshPanel nodes={mockNodes} onRemoveNode={onRemoveNode} />);

    const removeBtn = screen.getByTestId('remove-node-rpi-living-room');
    fireEvent.click(removeBtn);
    expect(onRemoveNode).toHaveBeenCalledWith('rpi-living-room');
  });
});
