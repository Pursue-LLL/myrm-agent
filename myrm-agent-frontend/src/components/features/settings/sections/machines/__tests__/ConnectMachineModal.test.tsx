/** @vitest-environment jsdom */

import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConnectMachineModal } from '../ConnectMachineModal';
import { MachinesService } from '../machinesService';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    connectModalTitle: '接入自托管机器节点',
    connectModalSubtitle: '复制专属一次性命令并在目标主机终端中运行',
    platformLabel: '目标操作系统',
    commandLabel: '一键接入命令',
    copied: '已复制',
    copyCommand: '复制命令',
    testingHeartbeat: '正在等待节点向控制平面发起首次握手心跳...',
    handshakeSuccess: '节点已成功接入控制平面并上报遥测',
    close: '完成',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ConnectMachineModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(<ConnectMachineModal isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with default darwin platform and generated command', async () => {
    vi.spyOn(MachinesService, 'generateToken').mockResolvedValueOnce({
      token: 'tok-mock-darwin-123',
      platform: 'darwin',
      quick_command: 'curl -fsSL https://get.myrm.ai/connect.sh | bash -s -- --token tok-mock-darwin-123',
      expires_at: '2026-10-13T04:00:00Z',
    });

    render(<ConnectMachineModal isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('接入自托管机器节点')).toBeInTheDocument();

    const commandPre = await screen.findByText(/connect\.sh/);
    expect(commandPre).toBeInTheDocument();
  });

  it('switches platform and triggers new token generation', async () => {
    const generateTokenSpy = vi
      .spyOn(MachinesService, 'generateToken')
      .mockResolvedValueOnce({
        token: 'tok-darwin',
        platform: 'darwin',
        quick_command: 'curl darwin',
        expires_at: '2026-10-13T04:00:00Z',
      })
      .mockResolvedValueOnce({
        token: 'tok-win',
        platform: 'windows',
        quick_command: 'powershell connect.ps1',
        expires_at: '2026-10-13T04:00:00Z',
      });

    render(<ConnectMachineModal isOpen={true} onClose={vi.fn()} />);

    await screen.findByText('curl darwin');

    const winButton = screen.getByRole('button', { name: /Windows \(x64\)/i });
    fireEvent.click(winButton);

    await screen.findByText('powershell connect.ps1');
    expect(generateTokenSpy).toHaveBeenCalledWith('windows');
  });

  it('copies command and triggers success callback on simulated handshake', async () => {
    vi.useFakeTimers();

    vi.spyOn(MachinesService, 'generateToken').mockResolvedValueOnce({
      token: 'tok-test',
      platform: 'darwin',
      quick_command: 'curl test-command',
      expires_at: '2026-10-13T04:00:00Z',
    });

    const mockWriteText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: mockWriteText,
      },
    });

    const handleSuccess = vi.fn();
    render(<ConnectMachineModal isOpen={true} onClose={vi.fn()} onConnectedSuccess={handleSuccess} />);

    await act(async () => {
      await Promise.resolve();
    });

    const copyBtn = screen.getByRole('button', { name: /复制命令/i });
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(mockWriteText).toHaveBeenCalledWith('curl test-command');

    // Fast-forward simulated handshake timeout (2500ms)
    act(() => {
      vi.advanceTimersByTime(2600);
    });

    expect(handleSuccess).toHaveBeenCalledTimes(1);

    vi.useRealTimers();
  });

  it('invokes onClose when close button or X is clicked', () => {
    const handleClose = vi.fn();
    render(<ConnectMachineModal isOpen={true} onClose={handleClose} />);

    const closeBtn = screen.getByRole('button', { name: '完成' });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);

    const xBtn = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(xBtn);
    expect(handleClose).toHaveBeenCalledTimes(2);
  });
});
