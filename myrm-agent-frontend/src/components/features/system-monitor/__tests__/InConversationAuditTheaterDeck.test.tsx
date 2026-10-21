/**
 * [INPUT]: InConversationAuditTheaterDeck component, mock SessionDataAccessLedgerItem.
 * [OUTPUT]: Vitest test suite verifying lie-immune certification, timeline actions/plans, data access ledger, and tab switching.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/__tests__/InConversationAuditTheaterDeck.test.tsx
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { InConversationAuditTheaterDeck } from '../InConversationAuditTheaterDeck';
import { SessionDataAccessLedgerItem } from '../auditTheaterTypes';

describe('InConversationAuditTheaterDeck Component', () => {
  const mockLedger: SessionDataAccessLedgerItem = {
    session_id: 'sess-deck-101',
    resources: [
      {
        entry_id: 'res-1',
        session_id: 'sess-deck-101',
        resource_id: '/workspace/src/database.py',
        kind: 'file',
        mode: 'read',
        scope_detail: 'lines 1-120',
        size_bytes: 4096,
        line_count: 120,
        success: true,
        timestamp_ms: 1791800000000,
      },
      {
        entry_id: 'res-2',
        session_id: 'sess-deck-101',
        resource_id: '/workspace/src/migration.sql',
        kind: 'file',
        mode: 'write',
        scope_detail: 'write 85 lines',
        size_bytes: 2048,
        line_count: 85,
        success: true,
        timestamp_ms: 1791800001000,
      },
      {
        entry_id: 'res-3',
        session_id: 'sess-deck-101',
        resource_id: 'memory://user_profile_preference',
        kind: 'memory',
        mode: 'read',
        scope_detail: 'top_k=3',
        size_bytes: 512,
        line_count: 10,
        success: true,
        timestamp_ms: 1791800002000,
      },
      {
        entry_id: 'res-4',
        session_id: 'sess-deck-101',
        resource_id: 'https://docs.anthropic.com/api',
        kind: 'web_network',
        mode: 'read',
        scope_detail: 'GET /api',
        size_bytes: 8192,
        line_count: 0,
        success: true,
        timestamp_ms: 1791800003000,
      },
    ],
    events: [
      {
        event_id: 'evt-1',
        session_id: 'sess-deck-101',
        step_name: 'Forward Plan: Read schema definition',
        tool_name: 'view_file',
        is_plan: true,
        status: 'in_progress',
        duration_ms: 0,
        inputs_summary: 'Target: database.py',
        timestamp_ms: 1791800000000,
      },
      {
        event_id: 'evt-2',
        session_id: 'sess-deck-101',
        step_name: 'Executed Action: Read schema definition',
        tool_name: 'view_file',
        is_plan: false,
        status: 'completed',
        duration_ms: 42,
        inputs_summary: 'Target: database.py',
        timestamp_ms: 1791800000500,
      },
    ],
    total_resources_accessed: 4,
    total_files_read: 1,
    total_files_written: 1,
    total_memories_queried: 1,
    total_network_domains_visited: 1,
    lie_immune_verified: true,
    digest_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    generated_at_ms: 1791800005000,
  };

  it('renders top lie-immune badge, SHA-256 fingerprint, and resource KPIs', () => {
    render(<InConversationAuditTheaterDeck ledger={mockLedger} />);

    expect(screen.getByTestId('audit-theater-deck')).toBeInTheDocument();
    expect(screen.getByText(/Authoritative Audit Theater/)).toBeInTheDocument();
    expect(screen.getByText(/撒谎免疫 \(Lie-Immune\)/)).toBeInTheDocument();
    expect(screen.getByText(/e3b0c44298fc1c14\.\.\./)).toBeInTheDocument();

    // Check KPIs
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(4);
  });

  it('renders action timeline with planned intentions and executed actions', () => {
    render(<InConversationAuditTheaterDeck ledger={mockLedger} />);

    expect(screen.getByText('PLANNED INTENTION')).toBeInTheDocument();
    expect(screen.getByText('EXECUTED ACTION')).toBeInTheDocument();
    expect(screen.getByText('Forward Plan: Read schema definition')).toBeInTheDocument();
    expect(screen.getByText('Executed Action: Read schema definition')).toBeInTheDocument();
    expect(screen.getByText('42 ms')).toBeInTheDocument();
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
  });

  it('switches to data access ledger tab and filters resources', async () => {
    render(<InConversationAuditTheaterDeck ledger={mockLedger} />);

    // Switch to Data Access Ledger
    const ledgerTabBtn = screen.getByRole('button', { name: /Data Access Ledger/i });
    fireEvent.click(ledgerTabBtn);

    expect(screen.getByText('/workspace/src/database.py')).toBeInTheDocument();
    expect(screen.getByText('/workspace/src/migration.sql')).toBeInTheDocument();
    expect(screen.getByText('memory://user_profile_preference')).toBeInTheDocument();
    expect(screen.getByText('https://docs.anthropic.com/api')).toBeInTheDocument();

    expect(screen.getAllByText('READ').length).toBe(3);
    expect(screen.getByText('WRITE')).toBeInTheDocument();

    // Test Kind filter dropdown
    const selectEl = screen.getByRole('combobox', { name: /Resource Kind/i });
    fireEvent.change(selectEl, { target: { value: 'file' } });

    expect(screen.getByText('/workspace/src/database.py')).toBeInTheDocument();
    expect(screen.getByText('/workspace/src/migration.sql')).toBeInTheDocument();
    expect(screen.queryByText('memory://user_profile_preference')).not.toBeInTheDocument();
  });
});
