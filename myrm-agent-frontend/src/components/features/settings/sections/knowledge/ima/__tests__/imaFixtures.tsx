import { render } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';
import type { ImaItemCounts, ImaStatus } from '@/services/wiki/ima';
import { WikiAgentScopeProvider } from '../../WikiAgentScopeContext';
import ImaSourceCard from '../ImaSourceCard';
import { resetImaMocks } from './imaMocks';

export const NO_COUNTS: ImaItemCounts = {
  total: 0,
  synced: 0,
  pending: 0,
  failed: 0,
  unsupported: 0,
  too_large: 0,
  blocked: 0,
  dismissed: 0,
  remote_deleted: 0,
  duplicate: 0,
  partial: 0,
};

export function makeStatus(overrides: Partial<ImaStatus> = {}): ImaStatus {
  return {
    connected: true,
    account_hint: 'abcd…wxyz',
    needs_reauth: false,
    knowledge_bases: [],
    include_notes: true,
    job: { state: 'none', next_run_at: null },
    phase: 'idle',
    backfill_complete: false,
    last_run_at: null,
    last_error_kind: '',
    notes_unavailable: false,
    auto_compile: true,
    counts: NO_COUNTS,
    total_chars: 0,
    ...overrides,
  };
}

export const SYNCING = makeStatus({
  knowledge_bases: [{ id: 'kb1', name: 'Research' }],
  job: { state: 'active', next_run_at: null },
  phase: 'fetch',
  counts: { ...NO_COUNTS, total: 10, pending: 4, synced: 6, failed: 1, partial: 2 },
  total_chars: 12_000,
});

export const UP_TO_DATE = {
  ...SYNCING,
  phase: 'idle' as const,
  backfill_complete: true,
  last_run_at: '2026-10-26T08:00:00Z',
  job: { state: 'active' as const, next_run_at: '2999-01-01T00:00:00Z' },
  counts: { ...SYNCING.counts, pending: 0, synced: 10 },
};

export function renderCard({ onGoToDuplicateReview = vi.fn() }: { onGoToDuplicateReview?: () => void } = {}) {
  return render(
    <WikiAgentScopeProvider agentScopeId={null} scopeRevision={0} scopeLabel="default">
      <ImaSourceCard onGoToDuplicateReview={onGoToDuplicateReview} />
    </WikiAgentScopeProvider>,
  );
}

/** Fresh mocks and real timers around every test of the calling file. */
export function installImaCardLifecycle(): void {
  beforeEach(resetImaMocks);
  afterEach(() => {
    vi.useRealTimers();
  });
}
