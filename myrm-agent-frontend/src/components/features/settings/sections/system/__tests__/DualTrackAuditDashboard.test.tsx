import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DualTrackAuditDashboard } from '../DualTrackAuditDashboard';
import { dualTrackAuditService } from '@/services/dualTrackAudit';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.count !== undefined) return `${key}: ${params.count}`;
  if (params?.rate !== undefined) return `Refusal ${params.rate}%`;
  if (params?.format !== undefined) return `Format: ${params.format}`;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

vi.mock('@/services/dualTrackAudit', () => ({
  dualTrackAuditService: {
    getStats: vi.fn(),
    getEntries: vi.fn(),
    getExportUrl: vi.fn(),
  },
}));

describe('DualTrackAuditDashboard', () => {
  const mockStats = {
    totalEntries: 42,
    permittedCount: 38,
    refusedCount: 4,
    failedCount: 0,
    humanTakeTheWheelCount: 3,
    complianceRate: 0.905,
    avgLatencyMs: 65.4,
    topRulesTriggered: [
      {
        ruleName: 'DOMAIN_ALLOWLIST_POLICY',
        triggerCount: 20,
        refusedCount: 3,
        permittedCount: 17,
        failedCount: 0,
        refusalRate: 0.15,
        sampleTargets: ['api.external.com'],
      },
    ],
  };

  const mockEntries = [
    {
      entryId: 'aud_entry_001',
      sessionId: 'sess_12345',
      agentId: 'code_assistant',
      toolName: 'bash_exec',
      intentSummary: 'Execute sandbox test runner',
      rawIntentArgs: { cmd: 'pytest -q' },
      ruleName: 'SANDBOX_COMMAND_GATE',
      state: 'COMPLETED' as const,
      outcome: 'PERMITTED' as const,
      isHumanTakeTheWheel: false,
      createdAt: '2026-09-02T10:00:00Z',
      completedAt: '2026-09-02T10:00:01Z',
      latencyMs: 120,
      outputLength: 256,
      errorMessage: null,
    },
    {
      entryId: 'aud_entry_002',
      sessionId: 'sess_12345',
      agentId: 'code_assistant',
      toolName: 'fs_write',
      intentSummary: 'Attempt write to protected hosts file',
      rawIntentArgs: { path: '/etc/hosts' },
      ruleName: 'CRITICAL_FS_PATH_LOCK',
      state: 'REFUSED' as const,
      outcome: 'REFUSED' as const,
      isHumanTakeTheWheel: true,
      createdAt: '2026-09-02T10:05:00Z',
      completedAt: '2026-09-02T10:05:00Z',
      latencyMs: 15,
      outputLength: 0,
      errorMessage: 'Access denied by security boundary policy',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    (dualTrackAuditService.getStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockStats);
    (dualTrackAuditService.getEntries as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockEntries);
    (dualTrackAuditService.getExportUrl as unknown as ReturnType<typeof vi.fn>).mockReturnValue('https://api.myrm.io/export');
  });

  it('renders KPI summary cards and top triggered rule', async () => {
    render(<DualTrackAuditDashboard />);

    await waitFor(() => {
      expect(screen.getByText('42')).toBeInTheDocument();
      expect(screen.getByText('90.5%')).toBeInTheDocument();
      expect(screen.getByText('4')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
    });

    expect(screen.getByText('DOMAIN_ALLOWLIST_POLICY')).toBeInTheDocument();
  });

  it('renders recent audit trail entries with outcomes and details expansion', async () => {
    render(<DualTrackAuditDashboard />);

    await waitFor(() => {
      expect(screen.getByText('bash_exec')).toBeInTheDocument();
      expect(screen.getByText('fs_write')).toBeInTheDocument();
      expect(screen.getByText('TakeTheWheel')).toBeInTheDocument();
    });

    // Expand details on the second entry
    const eyeButtons = screen.getAllByLabelText('View entry details');
    expect(eyeButtons.length).toBeGreaterThan(0);

    fireEvent.click(eyeButtons[0]);
    await waitFor(() => {
      expect(screen.getByText(/Session ID:/)).toBeInTheDocument();
    });
  });

  it('triggers export links for compliance dossiers', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<DualTrackAuditDashboard />);

    await waitFor(() => {
      expect(screen.getByText('JSON')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('JSON'));
    expect(dualTrackAuditService.getExportUrl).toHaveBeenCalledWith({ format: 'json' });
    expect(openSpy).toHaveBeenCalledWith('https://api.myrm.io/export', '_blank');

    openSpy.mockRestore();
  });
});
