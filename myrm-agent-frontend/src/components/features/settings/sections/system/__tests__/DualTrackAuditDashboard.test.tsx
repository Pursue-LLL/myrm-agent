import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DualTrackAuditDashboard } from '../DualTrackAuditDashboard';
import { dualTrackAuditService } from '@/services/dualTrackAudit';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.count !== undefined) return `Count: ${params.count}`;
  if (params?.rate !== undefined) return `Rate: ${params.rate}%`;
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
    refusedCount: 3,
    failedCount: 1,
    humanTakeTheWheelCount: 5,
    complianceRate: 0.905,
    avgLatencyMs: 65.4,
    topRulesTriggered: [
      {
        ruleName: 'DOMAIN_ALLOWLIST_GATE',
        triggerCount: 20,
        refusedCount: 3,
        permittedCount: 17,
        failedCount: 0,
        refusalRate: 0.15,
        sampleTargets: ['https://api.github.com'],
      },
    ],
  };

  const mockEntries = [
    {
      entryId: 'ent_001',
      sessionId: 'sess_123',
      agentId: 'coder',
      toolName: 'bash',
      intentSummary: 'Execute test runner script',
      rawIntentArgs: { cmd: 'npm test' },
      ruleName: 'SANDBOX_EXEC',
      state: 'COMPLETED' as const,
      outcome: 'PERMITTED' as const,
      isHumanTakeTheWheel: true,
      createdAt: '2026-09-02T10:00:00Z',
      completedAt: '2026-09-02T10:00:01Z',
      latencyMs: 110.5,
      outputLength: 256,
      errorMessage: null,
    },
    {
      entryId: 'ent_002',
      sessionId: 'sess_123',
      agentId: 'coder',
      toolName: 'fs_write',
      intentSummary: 'Write to /etc/hosts',
      rawIntentArgs: { path: '/etc/hosts' },
      ruleName: 'PATH_BOUNDARY_GUARD',
      state: 'REFUSED' as const,
      outcome: 'REFUSED' as const,
      isHumanTakeTheWheel: false,
      createdAt: '2026-09-02T10:05:00Z',
      completedAt: '2026-09-02T10:05:00Z',
      latencyMs: 0.0,
      outputLength: 0,
      errorMessage: 'Access denied outside workspace',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(dualTrackAuditService.getStats).mockResolvedValue(mockStats);
    vi.mocked(dualTrackAuditService.getEntries).mockResolvedValue(mockEntries);
    vi.mocked(dualTrackAuditService.getExportUrl).mockReturnValue('/api/v1/security/audit/dual-track/export?format=json');
    window.open = vi.fn();
  });

  it('renders summary statistics and top rules', async () => {
    render(<DualTrackAuditDashboard />);

    await waitFor(() => {
      expect(screen.getByText('42')).toBeInTheDocument();
      expect(screen.getByText('90.5%')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
      expect(screen.getByText('DOMAIN_ALLOWLIST_GATE')).toBeInTheDocument();
    });
  });

  it('renders recent audit entries with badges and allows expanding details', async () => {
    render(<DualTrackAuditDashboard />);

    await waitFor(() => {
      expect(screen.getByText('Execute test runner script')).toBeInTheDocument();
      expect(screen.getByText('Write to /etc/hosts')).toBeInTheDocument();
      expect(screen.getByText('TakeTheWheel')).toBeInTheDocument();
    });

    const eyeButtons = screen.getAllByRole('button');
    const firstEye = eyeButtons.find((b) => b.querySelector('svg'));
    if (firstEye) {
      fireEvent.click(firstEye);
      await waitFor(() => {
        expect(screen.getByText(/SANDBOX_EXEC/)).toBeInTheDocument();
      });
    }
  });

  it('triggers export for JSON, CSV, and Markdown', async () => {
    render(<DualTrackAuditDashboard />);

    await waitFor(() => {
      expect(screen.getByText('JSON')).toBeInTheDocument();
    });

    const jsonBtn = screen.getByText('JSON');
    fireEvent.click(jsonBtn);
    expect(dualTrackAuditService.getExportUrl).toHaveBeenCalledWith({ format: 'json' });
    expect(window.open).toHaveBeenCalled();

    const csvBtn = screen.getByText('CSV');
    fireEvent.click(csvBtn);
    expect(dualTrackAuditService.getExportUrl).toHaveBeenCalledWith({ format: 'csv' });

    const mdBtn = screen.getByText('Markdown');
    fireEvent.click(mdBtn);
    expect(dualTrackAuditService.getExportUrl).toHaveBeenCalledWith({ format: 'markdown' });
  });
});
