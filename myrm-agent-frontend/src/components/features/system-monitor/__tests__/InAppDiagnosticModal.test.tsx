import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { InAppDiagnosticModal } from '../InAppDiagnosticModal';
import { SandboxSelfHealButton } from '../SandboxSelfHealButton';
import type { DiagnosticBundle, SelfHealRebootResult, TicketSubmitResponse } from '../types';

describe('InAppDiagnosticModal & SandboxSelfHealButton', () => {
  const mockBundle: DiagnosticBundle = {
    bundle_id: 'bundle_abc123',
    session_id: 'sess-alpha-88',
    sandbox_id: 'sbx-prod-42',
    vitals: {
      cpu_pct: 92.5,
      mem_pct: 88.0,
      disk_free_bytes: 45000000,
      network_state: 'degraded',
      uptime_secs: 2400.0,
      is_volume_healthy: true,
    },
    logs: [
      {
        timestamp: '2026-10-12T10:00:00Z',
        level: 'ERROR',
        subsystem: 'sandbox_kernel',
        message: 'Timeout communicating with upstream agent service',
        metadata: { client: 'desktop' },
      },
    ],
    client_context: {
      client_version: '1.4.0',
      platform: 'darwin',
      browser_or_os: 'Chrome 130',
      active_route: '/workspace/run-1',
      session_id: 'sess-alpha-88',
    },
    scrubbed_pii_count: 3,
    checksum: 'valid-hmac-sha256-checksum',
    created_at: '2026-10-12T10:01:00Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders modal details, vitals, logs, and scrubbed pii badge', () => {
    const handleClose = vi.fn();
    render(<InAppDiagnosticModal isOpen={true} onClose={handleClose} bundle={mockBundle} />);

    expect(screen.getByText('端内沙箱现场全景诊断与闪电工单')).toBeInTheDocument();
    expect(screen.getByText(/3 处/)).toBeInTheDocument();
    expect(screen.getByText('92.5%')).toBeInTheDocument();
    expect(screen.getByText('88%')).toBeInTheDocument();
    expect(screen.getByText('degraded')).toBeInTheDocument();
    expect(screen.getByText(/Timeout communicating with upstream agent/)).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    const handleClose = vi.fn();
    render(<InAppDiagnosticModal isOpen={false} onClose={handleClose} bundle={mockBundle} />);

    expect(screen.queryByTestId('in-app-diagnostic-modal')).not.toBeInTheDocument();
  });

  it('triggers in-place self heal reboot successfully', async () => {
    const mockRebootResponse: SelfHealRebootResult = {
      sandbox_id: 'sbx-prod-42',
      status: 'REBOOT_SUCCESS',
      recovered_in_seconds: 2.1,
      volume_intact: true,
      message: '沙箱容器原地重启完成，持久化 Volume /data 状态正常',
      rebooted_at: '2026-10-12T10:02:00Z',
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockRebootResponse,
    } as unknown as Response);

    const onRebootSuccess = vi.fn();
    render(<SandboxSelfHealButton sandboxId="sbx-prod-42" onRebootSuccess={onRebootSuccess} />);

    const rebootBtn = screen.getByTestId('self-heal-reboot-btn');
    fireEvent.click(rebootBtn);

    await waitFor(() => {
      expect(screen.getByTestId('self-heal-success-banner')).toBeInTheDocument();
      expect(screen.getByText(/2.1s/)).toBeInTheDocument();
    });

    expect(onRebootSuccess).toHaveBeenCalledWith(mockRebootResponse);
  });

  it('submits diagnostic ticket and displays ticket dispatch confirmation box', async () => {
    const mockTicketResp: TicketSubmitResponse = {
      ticket_id: 'TICKET-20261012-A1B2C',
      bundle_id: 'bundle_abc123',
      status: 'DISPATCHED',
      sla_target_minutes: 15,
      assigned_tier: 'T2_OPS_ESCALATION',
      auto_diagnosis: '沙箱内存超警戒水位 (>85%)，捕获到 1 处异常错误日志',
      suggested_actions: ['建议尝试点击「一键自愈热重启」释放沙箱进程'],
      created_at: '2026-10-12T10:03:00Z',
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockTicketResp,
    } as unknown as Response);

    const handleTicketSubmitted = vi.fn();
    render(
      <InAppDiagnosticModal
        isOpen={true}
        onClose={vi.fn()}
        bundle={mockBundle}
        onTicketSubmitted={handleTicketSubmitted}
      />
    );

    const input = screen.getByTestId('ticket-description-input');
    fireEvent.change(input, { target: { value: 'Container unresponsive during build step' } });

    const submitBtn = screen.getByTestId('submit-ticket-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByTestId('ticket-dispatched-box')).toBeInTheDocument();
      expect(screen.getByText(/TICKET-20261012-A1B2C/)).toBeInTheDocument();
      expect(screen.getByText(/15 分钟/)).toBeInTheDocument();
      expect(screen.getByText(/一键自愈热重启/)).toBeInTheDocument();
    });

    expect(handleTicketSubmitted).toHaveBeenCalledWith(mockTicketResp);
  });
});
