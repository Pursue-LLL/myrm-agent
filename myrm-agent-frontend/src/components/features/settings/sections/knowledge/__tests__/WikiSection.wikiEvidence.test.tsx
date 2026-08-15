/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const queryWikiMock = vi.fn();
const listAgentsMock = vi.fn();
const apiRequestMock = vi.fn();
const recordWikiQueryAttemptMock = vi.fn();
const recordWikiQuerySubmittedMock = vi.fn();
const recordEvidenceSurfaceMock = vi.fn();

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
}));

vi.mock('@/lib/utils/clipboardUtils', () => ({
  isTauri: () => false,
}));

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    queryWiki: (...args: unknown[]) => queryWikiMock(...args),
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

vi.mock('../useWikiIngestSubscription', () => ({
  useWikiIngestSubscription: () => ({ connected: false, snapshot: null }),
}));

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
  default: ({
    open,
    level,
    surface,
  }: {
    open: boolean;
    level?: string;
    surface?: string;
  }) => (
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
    IconBook: Icon,
    IconGlow: Icon,
    IconWrench: Icon,
    IconDatabase: Icon,
    IconExplore: Icon,
    IconCopy: Icon,
    IconCheck: Icon,
    IconLoader: Icon,
    IconAlertTriangle: Icon,
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

import { WikiSection } from '../WikiSection';

describe('WikiSection evidence snippet flow', () => {
  beforeEach(() => {
    queryWikiMock.mockReset();
    listAgentsMock.mockReset();
    apiRequestMock.mockReset();
    recordWikiQueryAttemptMock.mockReset();
    recordWikiQuerySubmittedMock.mockReset();
    recordEvidenceSurfaceMock.mockReset();

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
  });

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
