import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { PortConflictModal } from '../PortConflictModal';
import type { PortInspectResponse } from '../types';

describe('PortConflictModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockConflictData: PortInspectResponse = {
    port: 3000,
    is_in_use: true,
    process: {
      pid: 1234,
      name: 'node',
      cmdline: ['node', 'server.js'],
      cpu_percent: 15.2,
      memory_mb: 180.5,
      status: 'running',
      username: 'developer',
      cwd: '/workspace/project',
      create_time: 1700000000,
      is_protected: false,
    },
    lineage: [
      {
        pid: 1,
        ppid: 0,
        name: 'launchd',
        cmdline: ['/sbin/launchd'],
        cwd: '/',
        username: 'root',
        is_high_resource: false,
      },
      {
        pid: 1234,
        ppid: 1,
        name: 'node',
        cmdline: ['node', 'server.js'],
        cwd: '/workspace/project',
        username: 'developer',
        is_high_resource: true,
      },
    ],
  };

  it('renders free port status correctly', async () => {
    const onResolved = vi.fn();
    const freeData: PortInspectResponse = {
      port: 8080,
      is_in_use: false,
      process: null,
      lineage: [],
    };

    render(
      <PortConflictModal
        port={8080}
        open={true}
        onOpenChange={vi.fn()}
        onResolved={onResolved}
        initialData={freeData}
      />
    );

    expect(screen.getByText(/端口 :8080 当前空闲无占用/)).toBeDefined();
    expect(onResolved).toHaveBeenCalledWith(8080);
  });

  it('renders conflicting process and lineage tree', () => {
    render(
      <PortConflictModal
        port={3000}
        open={true}
        onOpenChange={vi.fn()}
        initialData={mockConflictData}
      />
    );

    expect(screen.getAllByText('node').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/PID 1234/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/CPU 15.2% · 内存 180.5 MB/)).toBeDefined();
    expect(screen.getByTestId('process-lineage-view')).toBeDefined();
    expect(screen.getByText('高资源占用')).toBeDefined();
  });

  it('triggers safe kill with SIGTERM when clicked', async () => {
    const globalFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        pid: 1234,
        signal_sent: 'SIGTERM',
        message: 'Sent SIGTERM',
      }),
    });
    vi.stubGlobal('fetch', globalFetch);

    render(
      <PortConflictModal
        port={3000}
        open={true}
        onOpenChange={vi.fn()}
        initialData={mockConflictData}
      />
    );

    const safeKillBtn = screen.getByTestId('safe-kill-btn');
    fireEvent.click(safeKillBtn);

    await waitFor(() => {
      expect(globalFetch).toHaveBeenCalledWith(
        '/api/v1/system/processes/1234/kill',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            force: false,
            reason: 'port_3000_conflict_kill',
          }),
        })
      );
    });

    vi.unstubAllGlobals();
  });

  it('triggers force kill with SIGKILL when clicked', async () => {
    const globalFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        pid: 1234,
        signal_sent: 'SIGKILL',
        message: 'Sent SIGKILL',
      }),
    });
    vi.stubGlobal('fetch', globalFetch);

    render(
      <PortConflictModal
        port={3000}
        open={true}
        onOpenChange={vi.fn()}
        initialData={mockConflictData}
      />
    );

    const forceKillBtn = screen.getByTestId('force-kill-btn');
    fireEvent.click(forceKillBtn);

    await waitFor(() => {
      expect(globalFetch).toHaveBeenCalledWith(
        '/api/v1/system/processes/1234/kill',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            force: true,
            reason: 'port_3000_conflict_kill',
          }),
        })
      );
    });

    vi.unstubAllGlobals();
  });

  it('disables kill buttons when process is protected', () => {
    const protectedData: PortInspectResponse = {
      ...mockConflictData,
      process: {
        ...mockConflictData.process!,
        is_protected: true,
      },
    };

    render(
      <PortConflictModal
        port={3000}
        open={true}
        onOpenChange={vi.fn()}
        initialData={protectedData}
      />
    );

    expect(screen.getByText(/系统受保护进程/)).toBeDefined();
    const safeKillBtn = screen.getByTestId('safe-kill-btn') as HTMLButtonElement;
    const forceKillBtn = screen.getByTestId('force-kill-btn') as HTMLButtonElement;

    expect(safeKillBtn.disabled).toBe(true);
    expect(forceKillBtn.disabled).toBe(true);
  });
});
