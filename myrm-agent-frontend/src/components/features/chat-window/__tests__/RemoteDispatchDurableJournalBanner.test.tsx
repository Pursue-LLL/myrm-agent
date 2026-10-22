'use client';

/**
 * [INPUT]: RemoteDispatchDurableJournalBanner.tsx 与 mock 调度日志数据
 * [OUTPUT]: 验证 Hermes Fabric 远程分发与持久化对等日志横幅渲染、Pre-start 策略状态、有界证据水位与幂等恢复交互
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/RemoteDispatchDurableJournalBanner.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  RemoteDispatchDurableJournalBanner,
  JournalEntryItem,
} from '../RemoteDispatchDurableJournalBanner';

const mockJournalEntries: JournalEntryItem[] = [
  {
    journalId: 'jnl_001',
    seq: 1,
    entryType: 'dispatch_init',
    timestamp: 1720000000,
    payloadHash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  },
  {
    journalId: 'jnl_002',
    seq: 2,
    entryType: 'prestart_policy_pass',
    timestamp: 1720000005,
    payloadHash: 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb',
  },
  {
    journalId: 'jnl_003',
    seq: 3,
    entryType: 'evidence_admitted',
    timestamp: 1720000010,
    payloadHash: '4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce',
  },
];

describe('RemoteDispatchDurableJournalBanner', () => {
  it('renders top banner metadata with dispatchId, target peer, and coordinator principal', () => {
    render(
      <RemoteDispatchDurableJournalBanner
        dispatchId="dsp_test_01"
        targetPeerId="sandbox_node_worker"
        coordinatorPrincipal="coord_leader"
        prestartPassed={true}
        evidenceCount={3}
        totalEvidenceBytes={262144} // 256KB
        journalEntries={mockJournalEntries}
      />
    );

    expect(screen.getByTestId('remote-dispatch-durable-journal-banner')).toBeInTheDocument();
    expect(screen.getByTestId('dispatch-id-badge')).toHaveTextContent('dsp_test_01');
    expect(screen.getByTestId('peer-target-badge')).toHaveTextContent('sandbox_node_worker');
    expect(screen.getByText('coord_leader')).toBeInTheDocument();
    expect(screen.getByTestId('prestart-status-badge')).toHaveTextContent('Pre-start Validated');
  });

  it('renders fail-closed policy badge when prestartPassed is false', () => {
    render(
      <RemoteDispatchDurableJournalBanner
        dispatchId="dsp_test_02"
        targetPeerId="sandbox_node_failed"
        prestartPassed={false}
      />
    );

    expect(screen.getByTestId('prestart-status-badge')).toHaveTextContent('Policy Fail-Closed');
  });

  it('toggles journal details section on chevron button click', () => {
    render(
      <RemoteDispatchDurableJournalBanner
        dispatchId="dsp_test_03"
        targetPeerId="sandbox_node_worker"
        journalEntries={mockJournalEntries}
      />
    );

    // Initially collapsed
    expect(screen.queryByTestId('expanded-journal-section')).not.toBeInTheDocument();

    // Toggle expand
    const toggleBtn = screen.getByTestId('toggle-journal-btn');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('expanded-journal-section')).toBeInTheDocument();
    expect(screen.getByTestId('journal-entry-1')).toHaveTextContent('dispatch_init');
    expect(screen.getByTestId('journal-entry-2')).toHaveTextContent('prestart_policy_pass');
    expect(screen.getByTestId('journal-entry-3')).toHaveTextContent('evidence_admitted');

    // Toggle collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('expanded-journal-section')).not.toBeInTheDocument();
  });

  it('renders idempotent resume CTA and fires onResumeRecovery callback', () => {
    const handleResume = vi.fn();
    render(
      <RemoteDispatchDurableJournalBanner
        dispatchId="dsp_test_04"
        targetPeerId="sandbox_node_crash"
        canResume={true}
        onResumeRecovery={handleResume}
      />
    );

    const resumeBtn = screen.getByTestId('resume-recovery-btn');
    expect(resumeBtn).toBeInTheDocument();
    expect(resumeBtn).toHaveTextContent('Idempotent Resume');

    fireEvent.click(resumeBtn);
    expect(handleResume).toHaveBeenCalledWith('dsp_test_04');
  });
});
