import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TurnContextProvenanceAuditModal } from '../TurnContextProvenanceAuditModal';
import type {
  TurnContextInjectionManifest,
  TurnProvenanceDiffItem,
} from '../turnContextProvenanceTypes';

describe('TurnContextProvenanceAuditModal', () => {
  const mockManifest: TurnContextInjectionManifest = {
    session_id: 'sess_provenance_ui_01',
    turn_id: 'turn_001',
    model_snapshot_id: 'claude-3-7-sonnet-20250219',
    total_tokens: 37,
    total_chars: 120,
    created_at: '2026-10-12T00:00:00Z',
    chunks: [
      {
        chunk_id: 'turn_001_c0',
        source_id: 'sys_main',
        kind: 'system_prompt',
        content_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        content_chars: 45,
        estimated_tokens: 15,
        order_index: 0,
        meta: {},
      },
      {
        chunk_id: 'turn_001_c1',
        source_id: 'mem_pref',
        kind: 'memory',
        content_sha256: 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb',
        content_chars: 35,
        estimated_tokens: 10,
        order_index: 1,
        meta: {},
      },
      {
        chunk_id: 'turn_001_c2',
        source_id: 'skill_git',
        kind: 'skill',
        content_sha256: '3e23e8160039594a33894f6564e1b1348bbd7a0088d42c4acb73eeaed59c009d',
        content_chars: 40,
        estimated_tokens: 12,
        order_index: 2,
        meta: {},
      },
    ],
  };

  const mockDiffItems: TurnProvenanceDiffItem[] = [
    {
      source_id: 'sys_main',
      kind: 'system_prompt',
      diff_type: 'MODIFIED',
      previous_sha256: 'aaaa1111222233334444',
      current_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      token_delta: 5,
    },
    {
      source_id: 'mcp_new',
      kind: 'mcp_server',
      diff_type: 'ADDED',
      previous_sha256: null,
      current_sha256: 'bbbb2222333344445555',
      token_delta: 20,
    },
    {
      source_id: 'tool_old',
      kind: 'skill',
      diff_type: 'REMOVED',
      previous_sha256: 'cccc3333444455556666',
      current_sha256: null,
      token_delta: -8,
    },
  ];

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <TurnContextProvenanceAuditModal
        isOpen={false}
        onClose={vi.fn()}
        manifest={mockManifest}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders manifest details, tokens breakdown, and chunks table', () => {
    const handleClose = vi.fn();
    render(
      <TurnContextProvenanceAuditModal
        isOpen={true}
        onClose={handleClose}
        manifest={mockManifest}
      />
    );

    // Title & Meta
    expect(
      screen.getByText('逐轮上下文注入来源清单与可复现审计')
    ).toBeInTheDocument();
    expect(screen.getByText('sess_provenance_ui_01')).toBeInTheDocument();
    expect(screen.getByText('turn_001')).toBeInTheDocument();
    expect(screen.getByText('claude-3-7-sonnet-20250219')).toBeInTheDocument();

    // Token count
    expect(screen.getByText('37 Tokens')).toBeInTheDocument();

    // Source Chunk Rows
    expect(screen.getByText('sys_main')).toBeInTheDocument();
    expect(screen.getByText('mem_pref')).toBeInTheDocument();
    expect(screen.getByText('skill_git')).toBeInTheDocument();

    // Copy action
    const copyBtns = screen.getAllByText('复制');
    expect(copyBtns.length).toBe(3);

    // Close button
    fireEvent.click(screen.getByText('✕'));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('switches to diff view tab and renders cross-turn provenance diffs', () => {
    render(
      <TurnContextProvenanceAuditModal
        isOpen={true}
        onClose={vi.fn()}
        manifest={mockManifest}
        diffItems={mockDiffItems}
        previousTurnId="turn_000"
      />
    );

    // Switch Tab
    const diffTab = screen.getByText(/跨轮次差异比对/);
    fireEvent.click(diffTab);

    // Check Diff items
    expect(screen.getByText('✚ ADDED')).toBeInTheDocument();
    expect(screen.getByText('✖ REMOVED')).toBeInTheDocument();
    expect(screen.getByText('✎ MODIFIED')).toBeInTheDocument();

    expect(screen.getByText('mcp_new')).toBeInTheDocument();
    expect(screen.getByText('tool_old')).toBeInTheDocument();
    expect(screen.getByText('+5')).toBeInTheDocument();
    expect(screen.getByText('+20')).toBeInTheDocument();
    expect(screen.getByText('-8')).toBeInTheDocument();
  });
});
