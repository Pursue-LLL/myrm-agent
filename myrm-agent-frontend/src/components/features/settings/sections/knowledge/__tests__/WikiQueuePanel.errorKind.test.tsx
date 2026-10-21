/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getQueueStatusMock = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  },
}));

vi.mock('../WikiScopeChip', () => ({
  WikiScopeChip: ({ scopeLabel }: { scopeLabel: string }) => <div data-testid="wiki-scope-chip">{scopeLabel}</div>,
}));

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getQueueStatus: (...args: unknown[]) => getQueueStatusMock(...args),
  },
}));

import { WikiQueuePanel } from '../WikiQueuePanel';

// Every kind a queue row can carry besides ``unknown``: the classified model errors plus the compile's own three.
const QUEUE_ERROR_KINDS = [
  'auth',
  'billing',
  'rate_limit',
  'overloaded',
  'timeout',
  'context_overflow',
  'safety_block',
  'format_error',
  'response_format_error',
  'model_not_found',
  'challenge_blocked',
  'io_missing',
  'cancelled',
  'embed_window_violation',
] as const;

function failedItem(id: number, errorKind: string | undefined) {
  return {
    id,
    file_path: `raw/source-${id}.md`,
    status: 'failed',
    retry_count: 1,
    error_kind: errorKind,
    error_message: 'Article generation failed',
    created_at: '2026-10-17T00:00:00.000Z',
  };
}

describe('WikiQueuePanel failure labels', () => {
  beforeEach(() => {
    getQueueStatusMock.mockReset();
  });

  it('names every error kind a queue row can carry instead of falling back to the unknown label', async () => {
    getQueueStatusMock.mockResolvedValue({
      stats: { pending: 0, processing: 0, completed: 0, failed: QUEUE_ERROR_KINDS.length },
      pending_items: [],
      failed_items: QUEUE_ERROR_KINDS.map((kind, index) => failedItem(index + 1, kind)),
    });

    render(<WikiQueuePanel scopeLabel="vault" />);

    await waitFor(() => expect(screen.getByText('failedItems')).toBeTruthy());
    for (const kind of QUEUE_ERROR_KINDS) {
      expect(screen.getByText(`errorKind.${kind}`)).toBeTruthy();
    }
    expect(screen.queryByText('errorKindUnknown')).toBeNull();
  });

  it('falls back to the unknown label for a row without a kind and for a kind it does not know', async () => {
    getQueueStatusMock.mockResolvedValue({
      stats: { pending: 0, processing: 0, completed: 0, failed: 2 },
      pending_items: [],
      failed_items: [failedItem(1, undefined), failedItem(2, 'unknown')],
    });

    render(<WikiQueuePanel scopeLabel="vault" />);

    await waitFor(() => expect(screen.getAllByText('errorKindUnknown')).toHaveLength(2));
  });
});
