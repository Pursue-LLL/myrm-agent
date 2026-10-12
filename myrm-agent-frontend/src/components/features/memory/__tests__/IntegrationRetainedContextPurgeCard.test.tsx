/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { IntegrationRetainedContextPurgeCard } from '../command-center/IntegrationRetainedContextPurgeCard';
import type {
  DisconnectWithPurgeResponseDTO,
  ProvenanceRevocationAuditItemDTO,
  RetainedContextSummaryDTO,
} from '@/services/memory/retainedContext';

const {
  mockGetRetainedContextSummary,
  mockDisconnectWithPurge,
  mockListProvenanceRevocationRecords,
  mockReinstateProvenance,
} = vi.hoisted(() => ({
  mockGetRetainedContextSummary: vi.fn(),
  mockDisconnectWithPurge: vi.fn(),
  mockListProvenanceRevocationRecords: vi.fn(),
  mockReinstateProvenance: vi.fn(),
}));

vi.mock('@/services/memory/retainedContext', () => ({
  getRetainedContextSummary: mockGetRetainedContextSummary,
  disconnectWithPurge: mockDisconnectWithPurge,
  listProvenanceRevocationRecords: mockListProvenanceRevocationRecords,
  reinstateProvenance: mockReinstateProvenance,
}));

describe('IntegrationRetainedContextPurgeCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockSummaryActive: RetainedContextSummaryDTO = {
    integration_id: 'google_workspace',
    provider_type: 'oauth_provider',
    retained_memory_count: 5,
    retained_tree_count: 2,
    retained_fact_count: 0,
    total_retained_items: 7,
    oldest_retained_at: '2026-10-01T10:00:00Z',
    latest_retained_at: '2026-10-06T12:00:00Z',
    sample_snippets: ['Spreadsheet summary: FY26 Q1 Revenue', 'Email thread: API Security'],
    is_provenance_revoked: false,
  };

  const mockAuditRecord: ProvenanceRevocationAuditItemDTO = {
    revocation_id: 'rev_test_1234',
    integration_id: 'slack',
    reason: 'User compliance wipe',
    revoked_at: '2026-10-06T15:30:00Z',
    purged_items_count: 4,
    actor: 'admin_tester',
  };

  const mockRetainResponse: DisconnectWithPurgeResponseDTO = {
    integration_id: 'google_workspace',
    provider_type: 'oauth_provider',
    disconnected: true,
    purged_items: 0,
    mode: 'retain_context',
    revocation_id: null,
    message: 'Disconnected. Context retained.',
    completed_at: '2026-10-08T01:00:00Z',
  };

  const mockPurgeResponse: DisconnectWithPurgeResponseDTO = {
    integration_id: 'google_workspace',
    provider_type: 'oauth_provider',
    disconnected: true,
    purged_items: 7,
    mode: 'purge_and_revoke',
    revocation_id: 'rev_purge_8888',
    message: 'Purged 7 items with provenance revoked.',
    completed_at: '2026-10-08T01:05:00Z',
  };

  it('renders initial state and fetches connector retained context summary', async () => {
    mockGetRetainedContextSummary.mockResolvedValueOnce(mockSummaryActive);
    mockListProvenanceRevocationRecords.mockResolvedValueOnce([mockAuditRecord]);

    render(<IntegrationRetainedContextPurgeCard />);

    expect(
      screen.getByText(/集成断连上下文治理与溯源撤销/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Google Workspace')).toBeInTheDocument();
    expect(screen.getByText('GitHub PR & Issues')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetRetainedContextSummary).toHaveBeenCalledWith('google_workspace', 'oauth_provider');
    });

    expect(await screen.findByText('7')).toBeInTheDocument();
    expect(await screen.findByText('5')).toBeInTheDocument();
    expect(await screen.findByText('2')).toBeInTheDocument();
    expect(screen.getByText(/来源可信 \(Active\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Spreadsheet summary: FY26 Q1 Revenue/i)).toBeInTheDocument();
  });

  it('executes disconnect in retain_context mode (Dots parity)', async () => {
    mockGetRetainedContextSummary.mockResolvedValue(mockSummaryActive);
    mockListProvenanceRevocationRecords.mockResolvedValue([]);
    mockDisconnectWithPurge.mockResolvedValueOnce(mockRetainResponse);

    render(<IntegrationRetainedContextPurgeCard />);

    await waitFor(() => {
      expect(mockGetRetainedContextSummary).toHaveBeenCalled();
    });

    // Switch to retain_context mode
    const retainModeBtn = screen.getByText(/模式 A: 仅断连 \(保留记忆\)/i);
    fireEvent.click(retainModeBtn);

    const submitBtn = screen.getByRole('button', { name: /仅断开连接 \(保留记忆\)/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockDisconnectWithPurge).toHaveBeenCalledWith(
        'google_workspace',
        expect.objectContaining({
          purge_mode: 'retain_context',
          confirm_purge: false,
        }),
        'oauth_provider',
      );
    });

    expect(await screen.findByText(/操作完成: Disconnected. Context retained./i)).toBeInTheDocument();
  });

  it('requires confirmation and executes destructive purge_and_revoke', async () => {
    mockGetRetainedContextSummary.mockResolvedValue(mockSummaryActive);
    mockListProvenanceRevocationRecords.mockResolvedValue([]);
    mockDisconnectWithPurge.mockResolvedValueOnce(mockPurgeResponse);

    render(<IntegrationRetainedContextPurgeCard />);

    await waitFor(() => {
      expect(mockGetRetainedContextSummary).toHaveBeenCalled();
    });

    // Default mode is purge_and_revoke, trying submit without checking confirmation box
    const submitBtn = screen.getByRole('button', { name: /执行彻底断连并 Purge 清理/i });
    expect(submitBtn).toBeDisabled();

    // Check confirmation checkbox
    const confirmCheckbox = screen.getByLabelText(/我确认彻底清除此连接器产生的所有长效记忆并作废该来源/i);
    fireEvent.click(confirmCheckbox);
    expect(confirmCheckbox).toBeChecked();
    expect(submitBtn).not.toBeDisabled();

    // Fill audit reason
    const reasonInput = screen.getByLabelText(/审计操作原因/i);
    fireEvent.change(reasonInput, { target: { value: 'GDPR Right to be Forgotten' } });

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockDisconnectWithPurge).toHaveBeenCalledWith(
        'google_workspace',
        expect.objectContaining({
          purge_mode: 'purge_and_revoke',
          confirm_purge: true,
          reason: 'GDPR Right to be Forgotten',
        }),
        'oauth_provider',
      );
    });

    expect(
      await screen.findByText(/操作完成: Purged 7 items with provenance revoked./i),
    ).toBeInTheDocument();
    expect(screen.getByText(/已物理清理条目: 7 项/i)).toBeInTheDocument();
  });

  it('renders provenance revocation audit records and supports reinstatement', async () => {
    mockGetRetainedContextSummary.mockResolvedValue(mockSummaryActive);
    mockListProvenanceRevocationRecords.mockResolvedValue([mockAuditRecord]);
    mockReinstateProvenance.mockResolvedValueOnce({ integration_id: 'slack', reinstated: true });

    render(<IntegrationRetainedContextPurgeCard />);

    expect(await screen.findByText('slack')).toBeInTheDocument();
    expect(screen.getByText('rev_test_1234')).toBeInTheDocument();
    expect(screen.getByText('User compliance wipe')).toBeInTheDocument();

    const reinstateBtn = screen.getByRole('button', { name: /恢复信任/i });
    fireEvent.click(reinstateBtn);

    await waitFor(() => {
      expect(mockReinstateProvenance).toHaveBeenCalledWith('slack');
    });
  });
});
