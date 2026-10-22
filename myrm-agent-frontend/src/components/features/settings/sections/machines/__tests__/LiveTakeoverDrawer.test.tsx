/** @vitest-environment jsdom */

import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveTakeoverDrawer } from '../LiveTakeoverDrawer';
import { MachinesService } from '../machinesService';
import { MachineNode } from '../machinesTypes';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    takingOverTitle: '人工接管中',
    takingOverDesc: '您的键鼠输入将直通目标机器，AI 正在暂停等待',
    takeoverBtn: '接管控制',
    resumeBtn: '交还给智能体',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockMachine: MachineNode = {
  machine_id: 'mach-target-01',
  hostname: 'mac-target.local',
  display_name: 'Studio M2 Ultra',
  platform: 'darwin',
  ip_address: '192.168.1.150',
  status: 'online',
  metrics: {
    cpu_usage_pct: 18.0,
    memory_usage_pct: 35.0,
    disk_usage_pct: 40.0,
    active_tasks_count: 1,
    last_heartbeat_at: '2026-10-13T00:00:00Z',
  },
  registered_at: '2026-10-13T00:00:00Z',
  tags: ['Apple Silicon'],
};

describe('LiveTakeoverDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false or machine is null', () => {
    const { container: c1 } = render(<LiveTakeoverDrawer isOpen={false} machine={mockMachine} onClose={vi.fn()} />);
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(<LiveTakeoverDrawer isOpen={true} machine={null} onClose={vi.fn()} />);
    expect(c2.firstChild).toBeNull();
  });

  it('renders drawer header and remote screen viewport', () => {
    render(<LiveTakeoverDrawer isOpen={true} machine={mockMachine} onClose={vi.fn()} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Studio M2 Ultra')).toBeInTheDocument();
    expect(screen.getByText('192.168.1.150')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Remote Screen Viewport/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /接管控制/i })).toBeInTheDocument();
  });

  it('toggles takeover control state to human and back to agent', async () => {
    const initiateSpy = vi.spyOn(MachinesService, 'initiateTakeover').mockResolvedValueOnce({
      session_id: 'tk-1',
      machine_id: 'mach-target-01',
      state: 'human_takeover',
      started_at: '2026-10-13T00:00:00Z',
      updated_at: '2026-10-13T00:00:00Z',
    });

    const releaseSpy = vi.spyOn(MachinesService, 'releaseTakeover').mockResolvedValueOnce({
      session_id: 'tk-1',
      machine_id: 'mach-target-01',
      state: 'agent',
      started_at: '2026-10-13T00:00:00Z',
      updated_at: '2026-10-13T00:00:00Z',
    });

    const handleStatusChange = vi.fn();

    render(
      <LiveTakeoverDrawer isOpen={true} machine={mockMachine} onClose={vi.fn()} onStatusChange={handleStatusChange} />,
    );

    const takeoverBtn = screen.getByRole('button', { name: /接管控制/i });
    await act(async () => {
      fireEvent.click(takeoverBtn);
    });

    expect(initiateSpy).toHaveBeenCalledWith('mach-target-01');
    expect(handleStatusChange).toHaveBeenCalledTimes(1);
    expect(screen.getByText('人工接管中:')).toBeInTheDocument();

    const resumeBtn = screen.getByRole('button', { name: /交还给智能体/i });
    await act(async () => {
      fireEvent.click(resumeBtn);
    });

    expect(releaseSpy).toHaveBeenCalledWith('mach-target-01');
    expect(handleStatusChange).toHaveBeenCalledTimes(2);
  });

  it('updates cursor position when mouse moves inside viewport during human takeover', async () => {
    vi.spyOn(MachinesService, 'initiateTakeover').mockResolvedValueOnce({
      session_id: 'tk-2',
      machine_id: 'mach-target-01',
      state: 'human_takeover',
      started_at: '2026-10-13T00:00:00Z',
      updated_at: '2026-10-13T00:00:00Z',
    });

    render(<LiveTakeoverDrawer isOpen={true} machine={mockMachine} onClose={vi.fn()} />);

    const takeoverBtn = screen.getByRole('button', { name: /接管控制/i });
    await act(async () => {
      fireEvent.click(takeoverBtn);
    });

    const viewport = screen.getByRole('region', { name: /Remote Screen Viewport/i });
    fireEvent.mouseMove(viewport, { clientX: 250, clientY: 150 });

    expect(screen.getByText(/光标位置:/)).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(<LiveTakeoverDrawer isOpen={true} machine={mockMachine} onClose={handleClose} />);

    const closeBtn = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
