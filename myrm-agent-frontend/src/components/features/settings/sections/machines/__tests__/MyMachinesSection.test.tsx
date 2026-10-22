/** @vitest-environment jsdom */

import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MyMachinesSection } from '../MyMachinesSection';
import { MachinesService } from '../machinesService';
import { MachineNode } from '../machinesTypes';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: '自托管机器节点与私有算力',
    subtitle: '管理接入系统的物理机与 GPU 工作站，支持实时桌面观察与人工接管',
    connectBtn: '接入新机器',
    refreshBtn: '刷新状态',
    emptyCluster: '暂无已接入的自托管节点',
    statusOnline: '在线 (就绪)',
    statusBusy: '繁忙 (任务中)',
    statusTakeover: '人工接管中',
    statusOffline: '离线',
    cpuUsage: 'CPU 负载',
    memUsage: '内存占用',
    diskUsage: '磁盘空间',
    activeTasks: '活跃任务',
    liveScreen: '实时桌面',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockMachines: MachineNode[] = [
  {
    machine_id: 'mach-01',
    hostname: 'mac-m2.local',
    display_name: 'Mac Studio M2',
    platform: 'darwin',
    ip_address: '192.168.1.100',
    status: 'online',
    metrics: {
      cpu_usage_pct: 22.5,
      memory_usage_pct: 45.0,
      disk_usage_pct: 35.0,
      active_tasks_count: 2,
      last_heartbeat_at: '2026-10-13T00:00:00Z',
    },
    registered_at: '2026-10-13T00:00:00Z',
    tags: ['darwin'],
  },
  {
    machine_id: 'mach-02',
    hostname: 'gpu-box.local',
    display_name: 'GPU Box H100',
    platform: 'linux',
    ip_address: '10.0.0.5',
    status: 'takeover',
    metrics: {
      cpu_usage_pct: 85.0,
      memory_usage_pct: 70.0,
      disk_usage_pct: 60.0,
      active_tasks_count: 4,
      last_heartbeat_at: '2026-10-13T00:00:00Z',
    },
    registered_at: '2026-10-13T00:00:00Z',
    tags: ['linux'],
  },
];

describe('MyMachinesSection', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders node cards with telemetry metrics and status badges', async () => {
    vi.spyOn(MachinesService, 'listMachines').mockResolvedValueOnce(mockMachines);

    render(<MyMachinesSection />);

    expect(await screen.findByText('Mac Studio M2')).toBeInTheDocument();
    expect(screen.getByText('GPU Box H100')).toBeInTheDocument();
    expect(screen.getByText('在线 (就绪)')).toBeInTheDocument();
    expect(screen.getByText('人工接管中')).toBeInTheDocument();

    expect(screen.getByText('22.5%')).toBeInTheDocument();
    expect(screen.getByText('85.0%')).toBeInTheDocument();
  });

  it('renders empty cluster message when machines list is empty', async () => {
    vi.spyOn(MachinesService, 'listMachines').mockResolvedValueOnce([]);

    render(<MyMachinesSection />);

    expect(await screen.findByText('暂无已接入的自托管节点')).toBeInTheDocument();
  });

  it('refreshes fleet when refresh button is clicked', async () => {
    const listSpy = vi
      .spyOn(MachinesService, 'listMachines')
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce(mockMachines);

    render(<MyMachinesSection />);

    await screen.findByText('暂无已接入的自托管节点');

    const refreshBtn = screen.getByRole('button', { name: /刷新状态/i });
    await act(async () => {
      fireEvent.click(refreshBtn);
    });

    expect(listSpy).toHaveBeenCalledTimes(2);
    expect(await screen.findByText('Mac Studio M2')).toBeInTheDocument();
  });

  it('opens ConnectMachineModal when connect button is clicked', async () => {
    vi.spyOn(MachinesService, 'listMachines').mockResolvedValueOnce(mockMachines);
    vi.spyOn(MachinesService, 'generateToken').mockResolvedValueOnce({
      token: 'tok-1',
      platform: 'darwin',
      quick_command: 'curl test',
      expires_at: '2026-10-13T00:00:00Z',
    });

    render(<MyMachinesSection />);

    await screen.findByText('Mac Studio M2');

    const connectBtn = screen.getByRole('button', { name: /接入新机器/i });
    fireEvent.click(connectBtn);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('opens LiveTakeoverDrawer when live screen button is clicked', async () => {
    vi.spyOn(MachinesService, 'listMachines').mockResolvedValueOnce(mockMachines);

    render(<MyMachinesSection />);

    await screen.findByText('Mac Studio M2');

    const liveScreenButtons = screen.getAllByRole('button', { name: /实时桌面/i });
    fireEvent.click(liveScreenButtons[0]);

    expect(screen.getByRole('region', { name: /Remote Screen Viewport/i })).toBeInTheDocument();
  });
});
