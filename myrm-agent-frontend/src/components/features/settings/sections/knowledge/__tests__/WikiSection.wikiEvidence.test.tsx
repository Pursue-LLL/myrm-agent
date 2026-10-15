/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const queryWikiMock = vi.fn();
const listAgentsMock = vi.fn();
const apiRequestMock = vi.fn();
const recordWikiQueryAttemptMock = vi.fn();
const recordWikiQuerySubmittedMock = vi.fn();
const recordEvidenceSurfaceMock = vi.fn();
const startWikiMaintainMock = vi.fn();
const getWikiMaintainStatusMock = vi.fn();
const cancelWikiMaintainMock = vi.fn();
const compileWikiMock = vi.fn();

// What the live ingest stream last said; the page reads it through useWikiIngestSubscription.
const ingestStream = vi.hoisted(() => ({
  snapshot: null as object | null,
  listeners: new Set<(snapshot: object) => void>(),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(''),
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/settings/wiki',
}));

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    custom: vi.fn(),
    message: vi.fn(),
  }),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public code: number = 50001,
    ) {
      super(message);
    }
  },
}));

vi.mock('@/lib/utils/clipboardUtils', () => ({
  isTauri: () => false,
}));

vi.mock('@/services/wikiService', () => ({
  startWikiMaintain: (...args: unknown[]) => startWikiMaintainMock(...args),
  getWikiMaintainStatus: (...args: unknown[]) => getWikiMaintainStatusMock(...args),
  cancelWikiMaintain: (...args: unknown[]) => cancelWikiMaintainMock(...args),
  wikiService: {
    queryWiki: (...args: unknown[]) => queryWikiMock(...args),
    compileWiki: (...args: unknown[]) => compileWikiMock(...args),
    getHealthReport: vi.fn().mockResolvedValue({
      mode: 'structural',
      generated_at: new Date().toISOString(),
      open_actions_count: 0,
      issues_found: 0,
      issues: [],
      drift_sampled: false,
      duplicate_groups_pending: 0,
      synthesis_pending: 0,
    }),
    getRawTree: vi.fn().mockResolvedValue([]),
    getQueueStatus: vi.fn().mockResolvedValue({
      stats: {},
      pending_items: [],
      failed_items: [],
      compile_run: null,
    }),
  },
}));

vi.mock('../useWikiIngestSubscription', async () => {
  const { useEffect, useRef, useState } = await import('react');
  return {
    useWikiIngestSubscription: (_scope: unknown, options?: { onSnapshot?: (snapshot: object) => void }) => {
      const [snapshot, setSnapshot] = useState<object | null>(ingestStream.snapshot);
      const onSnapshot = useRef(options?.onSnapshot);
      onSnapshot.current = options?.onSnapshot;
      useEffect(() => {
        const listener = (next: object) => {
          setSnapshot(next);
          onSnapshot.current?.(next);
        };
        ingestStream.listeners.add(listener);
        return () => {
          ingestStream.listeners.delete(listener);
        };
      }, []);
      return { connected: snapshot !== null, snapshot };
    },
  };
});

vi.mock('@/services/agent', () => ({
  listAgents: (...args: unknown[]) => listAgentsMock(...args),
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_id: string, name: string) => name,
}));

vi.mock('@/services/wiki/evidenceMetrics', () => ({
  recordWikiQueryAttempt: (...args: unknown[]) => recordWikiQueryAttemptMock(...args),
  recordWikiQuerySubmitted: (...args: unknown[]) => recordWikiQuerySubmittedMock(...args),
  recordEvidenceSurface: (...args: unknown[]) => recordEvidenceSurfaceMock(...args),
}));

vi.mock('@/components/features/message-box/SourceChunkDrawer', () => ({
  default: ({ open, level, surface }: { open: boolean; level?: string; surface?: string }) => (
    <div
      data-testid="settings-snippet-drawer"
      data-open={open ? '1' : '0'}
      data-level={level ?? ''}
      data-surface={surface ?? ''}
    />
  ),
}));

vi.mock('../SecondBrainSetupCard', () => ({
  default: () => <div data-testid="second-brain-setup-card" />,
}));

vi.mock('../WikiConceptsList', () => ({
  WikiConceptsList: () => <div data-testid="wiki-concepts-list" />,
}));

vi.mock('../WikiPendingEdits', () => ({
  WikiPendingEdits: () => <div data-testid="wiki-pending-edits" />,
}));

vi.mock('../WikiQueuePanel', () => ({
  WikiQueuePanel: () => <div data-testid="wiki-queue-panel" />,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => {
  const Icon = () => <span />;
  return {
    IconActivity: Icon,
    IconAlertTriangle: Icon,
    IconArrowDown: Icon,
    IconArrowUp: Icon,
    IconArrowUpDown: Icon,
    IconBook: Icon,
    IconBrain: Icon,
    IconCheck: Icon,
    IconCheckCircle: Icon,
    IconClock: Icon,
    IconCopy: Icon,
    IconCpu: Icon,
    IconDatabase: Icon,
    IconDownload: Icon,
    IconEdit: Icon,
    IconExplore: Icon,
    IconEye: Icon,
    IconFileText: Icon,
    IconFolder: Icon,
    IconGlow: Icon,
    IconHardDrive: Icon,
    IconHeart: Icon,
    IconInbox: Icon,
    IconLoader: Icon,
    IconPlay: Icon,
    IconPlus: Icon,
    IconRefresh: Icon,
    IconRotateCcw: Icon,
    IconSave: Icon,
    IconSearch: Icon,
    IconShield: Icon,
    IconShieldCheck: Icon,
    IconSquare: Icon,
    IconStop: Icon,
    IconTrash: Icon,
    IconUpload: Icon,
    IconVideo: Icon,
    IconWrench: Icon,
    IconX: Icon,
    IconXCircle: Icon,
  };
});

vi.mock('../WikiDuplicateReviewPanel', () => ({
  WikiDuplicateReviewPanel: () => <div data-testid="wiki-duplicate-review-panel" />,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    type = 'button',
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    type?: 'button' | 'submit';
  }) => (
    <button type={type} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}));

vi.mock('@/components/primitives/input', () => ({
  Input: ({
    value,
    onChange,
    onKeyDown,
    placeholder,
  }: {
    value?: string;
    onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
    onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
    placeholder?: string;
  }) => <input value={value} onChange={onChange} onKeyDown={onKeyDown} placeholder={placeholder} />,
}));

vi.mock('@/components/primitives/textarea', () => ({
  Textarea: ({
    value,
    onChange,
    placeholder,
  }: {
    value?: string;
    onChange?: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
    placeholder?: string;
  }) => <textarea value={value} onChange={onChange} placeholder={placeholder} />,
}));

vi.mock('@/components/primitives/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/primitives/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  TabsContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/primitives/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <div />,
}));

import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import type { WikiMaintainResponse, WikiMaintainStatus } from '@/services/wikiService';
import { WikiSection } from '../WikiSection';
import { MAINTAIN_FIRST_POLL_DELAY_MS, MAINTAIN_POLL_INTERVAL_MS } from '../useWikiMaintainRun';

function maintainStatus(overrides: Partial<WikiMaintainStatus> = {}): WikiMaintainStatus {
  return {
    state: 'idle',
    mode: null,
    phase: null,
    done: 0,
    total: 0,
    cancel_requested: false,
    result: null,
    error_code: null,
    ...overrides,
  };
}

function resetWikiMocks() {
  queryWikiMock.mockReset();
  startWikiMaintainMock.mockReset();
  getWikiMaintainStatusMock.mockReset();
  getWikiMaintainStatusMock.mockResolvedValue(maintainStatus());
  cancelWikiMaintainMock.mockReset();
  compileWikiMock.mockReset();
  ingestStream.snapshot = null;
  ingestStream.listeners.clear();
  listAgentsMock.mockReset();
  apiRequestMock.mockReset();
  recordWikiQueryAttemptMock.mockReset();
  recordWikiQuerySubmittedMock.mockReset();
  recordEvidenceSurfaceMock.mockReset();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.message).mockClear();
  vi.mocked(toast.error).mockClear();

  listAgentsMock.mockResolvedValue({ items: [] });
  apiRequestMock.mockImplementation((path: string) => {
    if (path.includes('/wiki/purpose')) {
      return Promise.resolve({ purpose: '' });
    }
    if (path.includes('/wiki/stats')) {
      return Promise.resolve({
        total_concepts: 0,
        total_articles: 0,
        total_raw_files: 0,
        wiki_path: '/tmp/wiki',
        vault_ready: true,
        legacy_migrated: true,
      });
    }
    return Promise.resolve({});
  });
  queryWikiMock.mockResolvedValue({
    answer: 'Wiki answer',
    related_articles: ['article-a'],
    source_snippets: [
      {
        path: 'team/.overview.md',
        name: 'team',
        snippet: 'evidence details',
        section: 'Overview',
        level: 'L1',
      },
    ],
  });
}

describe('WikiSection evidence snippet flow', () => {
  beforeEach(resetWikiMocks);

  it('records query/surface and opens snippet drawer with settings surface', async () => {
    render(<WikiSection />);

    const queryInput = await screen.findByPlaceholderText('query.placeholder');
    fireEvent.change(queryInput, { target: { value: 'where is policy?' } });

    const queryButton = screen.getByText('actions.query');
    fireEvent.click(queryButton);

    await waitFor(() => {
      expect(queryWikiMock).toHaveBeenCalledWith('where is policy?', 'auto', null);
    });
    expect(recordWikiQueryAttemptMock).toHaveBeenCalledWith('settings', 'agent:default');
    expect(recordWikiQuerySubmittedMock).toHaveBeenCalledWith('settings', 'agent:default');
    expect(recordEvidenceSurfaceMock).toHaveBeenCalledWith('settings', 1, 'agent:default');

    const snippetCard = await screen.findByRole('button', { name: /team/ });
    fireEvent.click(snippetCard);

    const drawer = screen.getByTestId('settings-snippet-drawer');
    expect(drawer.getAttribute('data-open')).toBe('1');
    expect(drawer.getAttribute('data-level')).toBe('L1');
    expect(drawer.getAttribute('data-surface')).toBe('settings');
  });
});

describe('WikiSection maintenance flow', () => {
  beforeEach(() => {
    resetWikiMocks();
    // The poll cadence is a production concern; the flow under test only needs the polls to happen.
    const realSetTimeout = window.setTimeout.bind(window);
    const pollDelays = [MAINTAIN_FIRST_POLL_DELAY_MS, MAINTAIN_POLL_INTERVAL_MS];
    vi.spyOn(window, 'setTimeout').mockImplementation(((handler: TimerHandler, delay?: number, ...args: unknown[]) =>
      realSetTimeout(handler, pollDelays.includes(delay ?? -1) ? 0 : delay, ...args)) as typeof window.setTimeout);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const RESULT: WikiMaintainResponse = {
    issues_found: 1,
    issues_fixed: 1,
    connections_discovered: 3,
    duration_ms: 240_000,
    open_actions_count: 0,
    raw_security_removed: 0,
    raw_security_removed_paths: [],
    issues: [],
    ai_unavailable: false,
  };

  function buttonWithText(text: string): Promise<HTMLButtonElement> {
    return screen.findByText(text).then((node) => node.closest('button') as HTMLButtonElement);
  }

  it('locks the button for the whole run, shows the progress, then reports the discovered links', async () => {
    let finishRun: (status: WikiMaintainStatus) => void = () => {};
    const lastPoll = new Promise<WikiMaintainStatus>((resolve) => {
      finishRun = resolve;
    });
    startWikiMaintainMock.mockResolvedValue(maintainStatus({ state: 'running', mode: 'structural' }));
    getWikiMaintainStatusMock
      .mockResolvedValueOnce(maintainStatus())
      .mockResolvedValueOnce(
        maintainStatus({ state: 'running', mode: 'structural', phase: 'link_discovery', done: 7, total: 20 }),
      )
      .mockReturnValueOnce(lastPoll);
    render(<WikiSection />);

    fireEvent.click(await screen.findByText('actions.maintain'));

    const progressButton = await buttonWithText('maintainProgress.linkDiscovery');
    expect(progressButton.disabled).toBe(true);
    expect(startWikiMaintainMock).toHaveBeenCalledWith('structural', null);
    expect(toast.success).not.toHaveBeenCalled();

    finishRun(maintainStatus({ state: 'succeeded', mode: 'structural', result: RESULT }));
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('success.maintainSummaryWithLinks');
    });
    expect((await buttonWithText('actions.maintain')).disabled).toBe(false);
    expect(startWikiMaintainMock).toHaveBeenCalledTimes(1);
  });

  it('tells the user to wait for the compile when it blocks the start', async () => {
    startWikiMaintainMock.mockRejectedValue(new ApiError('conflict', 409));
    render(<WikiSection />);

    fireEvent.click(await screen.findByText('actions.maintain'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('errors.maintainCompileBusy');
    });
    expect((await buttonWithText('actions.maintain')).disabled).toBe(false);
  });

  it('picks a run back up after the page is reopened and reports its result', async () => {
    let finishRun: (status: WikiMaintainStatus) => void = () => {};
    const lastPoll = new Promise<WikiMaintainStatus>((resolve) => {
      finishRun = resolve;
    });
    getWikiMaintainStatusMock
      .mockResolvedValueOnce(
        maintainStatus({ state: 'running', mode: 'full', phase: 'drift_review', done: 2, total: 5 }),
      )
      .mockReturnValueOnce(lastPoll);
    render(<WikiSection />);

    expect((await buttonWithText('maintainProgress.driftReview')).disabled).toBe(true);
    expect(startWikiMaintainMock).not.toHaveBeenCalled();

    finishRun(maintainStatus({ state: 'succeeded', mode: 'full', result: RESULT }));
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('success.maintainSummaryWithLinks');
    });
  });

  it('stops a full run on request, tells the user what is kept and unlocks the button', async () => {
    let endRun: (status: WikiMaintainStatus) => void = () => {};
    const lastPoll = new Promise<WikiMaintainStatus>((resolve) => {
      endRun = resolve;
    });
    getWikiMaintainStatusMock
      .mockResolvedValueOnce(
        maintainStatus({ state: 'running', mode: 'full', phase: 'link_discovery', done: 4, total: 20 }),
      )
      .mockReturnValueOnce(lastPoll);
    cancelWikiMaintainMock.mockResolvedValue(
      maintainStatus({
        state: 'running',
        mode: 'full',
        phase: 'link_discovery',
        done: 4,
        total: 20,
        cancel_requested: true,
      }),
    );
    render(<WikiSection />);

    const stopButton = await buttonWithText('actions.maintainCancel');
    expect(stopButton.disabled).toBe(false);
    fireEvent.click(stopButton);

    expect((await buttonWithText('actions.maintainCancelling')).disabled).toBe(true);
    expect(cancelWikiMaintainMock).toHaveBeenCalledWith(null);

    endRun(maintainStatus({ state: 'cancelled', mode: 'full', result: RESULT }));
    await waitFor(() => {
      expect(toast.message).toHaveBeenCalledWith('success.maintainCancelled');
    });
    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.queryByTestId('wiki-maintain-cancel-button')).toBeNull();
    expect((await buttonWithText('actions.maintain')).disabled).toBe(false);
  });

  it('offers no stop while a structural run is in flight', async () => {
    getWikiMaintainStatusMock
      .mockResolvedValueOnce(maintainStatus({ state: 'running', mode: 'structural' }))
      .mockReturnValue(new Promise<WikiMaintainStatus>(() => {}));
    render(<WikiSection />);

    expect((await buttonWithText('maintaining')).disabled).toBe(true);
    expect(screen.queryByTestId('wiki-maintain-cancel-button')).toBeNull();
  });

  it('tells the user when the stop request did not go through and lets them try again', async () => {
    getWikiMaintainStatusMock
      .mockResolvedValueOnce(maintainStatus({ state: 'running', mode: 'full' }))
      .mockReturnValue(new Promise<WikiMaintainStatus>(() => {}));
    cancelWikiMaintainMock.mockRejectedValue(new Error('network down'));
    render(<WikiSection />);

    fireEvent.click(await buttonWithText('actions.maintainCancel'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('errors.maintainCancelFailed');
    });
    expect((await buttonWithText('actions.maintainCancel')).disabled).toBe(false);
  });

  it('reports a failed run with the generic failure message', async () => {
    startWikiMaintainMock.mockResolvedValue(maintainStatus({ state: 'running', mode: 'full' }));
    getWikiMaintainStatusMock
      .mockResolvedValueOnce(maintainStatus())
      .mockResolvedValueOnce(maintainStatus({ state: 'failed', mode: 'full', error_code: 'maintain_failed' }));
    render(<WikiSection />);

    fireEvent.click(await screen.findByText('actions.maintain'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('errors.maintainFailed');
    });
  });
});

describe('WikiSection compile flow', () => {
  beforeEach(resetWikiMocks);

  const RUNNING_CIRCUIT = { state: 'running', pause_reason: '', primary_error_kind: '', phase: 'idle' } as const;

  function emitIngestSnapshot(stats: { pending?: number; processing?: number }, compileRun: object = RUNNING_CIRCUIT) {
    const snapshot = {
      stats: { pending: 0, processing: 0, completed: 0, failed: 0, ...stats },
      compile_run: compileRun,
    };
    ingestStream.snapshot = snapshot;
    act(() => {
      ingestStream.listeners.forEach((listener) => listener(snapshot));
    });
  }

  function buttonWithText(text: string): Promise<HTMLButtonElement> {
    return screen.findByText(text).then((node) => node.closest('button') as HTMLButtonElement);
  }

  it('hands the compile to the background and says how much is queued, without waiting for it', async () => {
    compileWikiMock.mockResolvedValue({ pending: 3, compile_run: RUNNING_CIRCUIT });
    render(<WikiSection />);

    fireEvent.click(await screen.findByText('actions.compile'));

    await waitFor(() => {
      expect(toast.message).toHaveBeenCalledWith('success.compileStarted');
    });
    expect(compileWikiMock).toHaveBeenCalledWith(null);
    expect(toast.success).not.toHaveBeenCalled();
    expect((await buttonWithText('actions.compile')).disabled).toBe(false);
  });

  it('says so when there is nothing new to compile', async () => {
    compileWikiMock.mockResolvedValue({ pending: 0, compile_run: RUNNING_CIRCUIT });
    render(<WikiSection />);

    fireEvent.click(await screen.findByText('actions.compile'));

    await waitFor(() => {
      expect(toast.message).toHaveBeenCalledWith('success.compileNothingNew');
    });
  });

  it('explains why nothing runs when the compile circuit is paused', async () => {
    compileWikiMock.mockResolvedValue({
      pending: 2,
      compile_run: { ...RUNNING_CIRCUIT, state: 'paused', pause_reason: 'Provider key was rejected' },
    });
    render(<WikiSection />);

    fireEvent.click(await screen.findByText('actions.compile'));

    await waitFor(() => {
      expect(toast.warning).toHaveBeenCalledWith('Provider key was rejected');
    });
    expect(toast.message).not.toHaveBeenCalled();
  });

  it('sends a dedup block to the duplicate review instead of reporting a failure', async () => {
    compileWikiMock.mockRejectedValue(new ApiError('conflict', 409));
    render(<WikiSection />);

    fireEvent.click(await screen.findByText('actions.compile'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('errors.compileBlockedByDedup');
    });
  });

  it('reports the end of the compile once, when the queue drains after this page started it', async () => {
    compileWikiMock.mockResolvedValue({ pending: 2, compile_run: RUNNING_CIRCUIT });
    render(<WikiSection />);
    fireEvent.click(await screen.findByText('actions.compile'));
    await waitFor(() => expect(toast.message).toHaveBeenCalledWith('success.compileStarted'));

    emitIngestSnapshot({ pending: 2 });
    emitIngestSnapshot({ processing: 2 });
    expect(toast.success).not.toHaveBeenCalled();
    emitIngestSnapshot({});
    emitIngestSnapshot({});

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('success.compileFinished');
    });

    emitIngestSnapshot({ processing: 1 });
    emitIngestSnapshot({});
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('stays quiet when a queue that this page did not start drains', async () => {
    render(<WikiSection />);
    await screen.findByText('actions.compile');

    emitIngestSnapshot({ processing: 1 });
    emitIngestSnapshot({});

    expect(toast.success).not.toHaveBeenCalled();
  });

  it('does not treat an idle compile circuit as a compile in flight: maintenance stays available', async () => {
    render(<WikiSection />);
    await screen.findByText('actions.compile');

    emitIngestSnapshot({}, { ...RUNNING_CIRCUIT, phase: 'idle' });

    expect((await buttonWithText('actions.maintain')).disabled).toBe(false);
    expect((await buttonWithText('actions.compile')).disabled).toBe(false);
  });

  it('locks maintenance and shows the compile as running while the worker has files in flight', async () => {
    render(<WikiSection />);
    await screen.findByText('actions.compile');

    emitIngestSnapshot({ processing: 2 });

    expect((await buttonWithText('actions.maintain')).disabled).toBe(true);
    expect((await buttonWithText('compiling')).disabled).toBe(false);
  });
});
