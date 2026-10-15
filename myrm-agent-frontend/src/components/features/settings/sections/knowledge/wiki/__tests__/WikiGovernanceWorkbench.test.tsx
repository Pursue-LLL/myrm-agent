/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NextIntlClientProvider } from 'next-intl';
import { WikiGovernanceWorkbench } from '../WikiGovernanceWorkbench';
import { wikiService } from '@/services/wikiService';
import de from '../../../../../../../../locales/de.json';
import en from '../../../../../../../../locales/en.json';
import ja from '../../../../../../../../locales/ja.json';
import ko from '../../../../../../../../locales/ko.json';
import zhTW from '../../../../../../../../locales/zh-TW.json';
import zh from '../../../../../../../../locales/zh.json';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getGovernanceOverview: vi.fn(),
    extendGovernanceConcepts: vi.fn(),
    archiveGovernanceConcepts: vi.fn(),
    undoGovernanceArchive: vi.fn(),
    reviveGovernanceConcepts: vi.fn(),
  },
}));

const LOCALES = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;
type LocaleCode = keyof typeof LOCALES;
const UNDO_WINDOW_MS = 30_000;
// Han, kana and Hangul: none of it may show up in a Latin-script interface.
const EAST_ASIAN_TEXT = /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/;

const governance = vi.mocked(wikiService);

function concept(name: string, ageDays: number) {
  return {
    concept_name: name,
    relative_path: `${name}.md`,
    age_days: ageDays,
    modified_at_iso: '2026-01-01T00:00:00+00:00',
    is_permanent: false,
    hit_count: 0,
    reason: 'server side reason',
  };
}

const OVERVIEW = {
  pending_count: 3,
  expiring_count: 2,
  gaps_count: 1,
  archived_count: 1,
  total_active: 40,
  expiring_concepts: [concept('alpha-note', 120), concept('beta-note', 95)],
  archived_concepts: [concept('old-note', 400)],
};

function actionResult(overrides: Partial<{ success: boolean; undo_token: string }> = {}) {
  return { success: true, affected_count: 1, message: 'English message from the server', undo_token: '', ...overrides };
}

function renderWorkbench(locale: LocaleCode = 'en', props: { onOpenPendingEdits?: () => void } = {}) {
  return render(
    <NextIntlClientProvider locale={locale} messages={{ settings: { wiki: LOCALES[locale].settings.wiki } }}>
      <WikiGovernanceWorkbench agentId="agent-1" onRefreshParent={() => {}} {...props} />
    </NextIntlClientProvider>,
  );
}

const copy = (locale: LocaleCode) => LOCALES[locale].settings.wiki;
const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const startingWith = (label: string) => new RegExp(`^${escapeRegExp(label)}`);

beforeEach(() => {
  governance.getGovernanceOverview.mockResolvedValue(OVERVIEW);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe('WikiGovernanceWorkbench copy', () => {
  it.each(Object.keys(LOCALES) as LocaleCode[])('words every visible label in %s', async (locale) => {
    const m = copy(locale);
    renderWorkbench(locale);

    expect(await screen.findByText(m.governanceTitle)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: m.refreshGovernance })).toBeInTheDocument();
    for (const label of [m.pendingQueue, m.expiringQueue, m.archivedQueue]) {
      expect(screen.getByRole('button', { name: startingWith(label) })).toBeInTheDocument();
    }
    expect(screen.getByText(m.gapsQueue)).toBeInTheDocument();
    expect(screen.getByText(m.needsReview)).toBeInTheDocument();
    expect(screen.getByText(m.expiringListTitle)).toBeInTheDocument();
    expect(screen.getByText(m.totalItems.replace('{count}', '2'))).toBeInTheDocument();
    expect(screen.getByText(m.daysUnchanged.replace('{days}', '120'))).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: m.extendButton })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: m.archiveButton })).toHaveLength(2);
  });

  it.each(['en', 'de'] as const)('shows no East Asian text anywhere in %s, on either tab', async (locale) => {
    const m = copy(locale);
    const { container } = renderWorkbench(locale);
    await screen.findByText(m.governanceTitle);
    expect(container.textContent).not.toMatch(EAST_ASIAN_TEXT);

    await userEvent.click(screen.getByRole('button', { name: startingWith(m.archivedQueue) }));
    expect(await screen.findByText(m.archivedListTitle)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(EAST_ASIAN_TEXT);
  });

  it('words the empty states of both lists', async () => {
    governance.getGovernanceOverview.mockResolvedValue({
      ...OVERVIEW,
      expiring_count: 0,
      archived_count: 0,
      expiring_concepts: [],
      archived_concepts: [],
    });
    const m = copy('en');
    renderWorkbench('en');

    expect(await screen.findByText(m.emptyExpiring)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: startingWith(m.archivedQueue) }));
    expect(screen.getByText(m.emptyArchived)).toBeInTheDocument();
  });

  it('does not tell the user where archived concepts are stored on disk', async () => {
    const m = copy('en');
    const { container } = renderWorkbench('en');
    await screen.findByText(m.governanceTitle);

    await userEvent.click(screen.getByRole('button', { name: startingWith(m.archivedQueue) }));

    expect(await screen.findByText('old-note')).toBeInTheDocument();
    expect(container.textContent).not.toContain('archive/');
    expect(screen.getByRole('button', { name: m.reviveButton })).toBeInTheDocument();
  });
});

describe('WikiGovernanceWorkbench queue cards', () => {
  it('uses native buttons for every clickable card', async () => {
    const m = copy('en');
    const { container } = renderWorkbench('en');
    await screen.findByText(m.governanceTitle);

    expect(container.querySelectorAll('[role="button"]')).toHaveLength(0);
    for (const label of [m.pendingQueue, m.expiringQueue, m.archivedQueue]) {
      expect(screen.getByRole('button', { name: startingWith(label) }).tagName).toBe('BUTTON');
    }
  });

  it('opens the pending edits from the keyboard with Enter and Space', async () => {
    const onOpenPendingEdits = vi.fn();
    const m = copy('en');
    renderWorkbench('en', { onOpenPendingEdits });
    const pending = await screen.findByRole('button', { name: startingWith(m.pendingQueue) });

    pending.focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard(' ');

    expect(onOpenPendingEdits).toHaveBeenCalledTimes(2);
  });

  it('tells assistive technology which list is showing', async () => {
    const m = copy('en');
    renderWorkbench('en');
    const expiring = await screen.findByRole('button', { name: startingWith(m.expiringQueue) });
    const archived = screen.getByRole('button', { name: startingWith(m.archivedQueue) });
    expect(expiring).toHaveAttribute('aria-pressed', 'true');
    expect(archived).toHaveAttribute('aria-pressed', 'false');

    await userEvent.click(archived);

    expect(expiring).toHaveAttribute('aria-pressed', 'false');
    expect(archived).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('WikiGovernanceWorkbench actions', () => {
  it('confirms an extension in the user language instead of the server text', async () => {
    governance.extendGovernanceConcepts.mockResolvedValue(actionResult());
    const m = copy('de');
    renderWorkbench('de');

    await userEvent.click((await screen.findAllByRole('button', { name: m.extendButton }))[0]);

    expect(governance.extendGovernanceConcepts).toHaveBeenCalledWith(['alpha-note'], 'agent-1');
    expect(await screen.findByText(m.extendSuccess.replace('{name}', 'alpha-note'))).toBeInTheDocument();
    expect(screen.queryByText('English message from the server')).not.toBeInTheDocument();
  });

  it('archives with an undo offer, then restores through it', async () => {
    governance.archiveGovernanceConcepts.mockResolvedValue(actionResult({ undo_token: 'token-1' }));
    governance.undoGovernanceArchive.mockResolvedValue(actionResult());
    const m = copy('en');
    renderWorkbench('en');

    await userEvent.click((await screen.findAllByRole('button', { name: m.archiveButton }))[1]);
    expect(await screen.findByText(m.archiveSuccess.replace('{name}', 'beta-note'))).toBeInTheDocument();
    expect(governance.archiveGovernanceConcepts).toHaveBeenCalledWith(['beta-note'], expect.any(String), 'agent-1');

    await userEvent.click(screen.getByRole('button', { name: m.undoAction }));

    expect(governance.undoGovernanceArchive).toHaveBeenCalledWith('token-1', 'agent-1');
    expect(await screen.findByText(m.undoSuccess)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: m.undoAction })).not.toBeInTheDocument();
  });

  it('withdraws the undo offer once the server stops honouring it', async () => {
    governance.archiveGovernanceConcepts.mockResolvedValue(actionResult({ undo_token: 'token-1' }));
    const m = copy('en');
    const scheduled: Array<{ handler: () => void; delay: number }> = [];
    const realSetTimeout = window.setTimeout.bind(window);
    vi.spyOn(window, 'setTimeout').mockImplementation(((handler: TimerHandler, delay?: number, ...args: unknown[]) => {
      if (delay === UNDO_WINDOW_MS) {
        scheduled.push({ handler: handler as () => void, delay });
        return 0;
      }
      return realSetTimeout(handler, delay, ...args);
    }) as typeof window.setTimeout);
    renderWorkbench('en');

    await userEvent.click((await screen.findAllByRole('button', { name: m.archiveButton }))[0]);
    const undo = await screen.findByRole('button', { name: m.undoAction });
    expect(undo).toBeInTheDocument();
    expect(scheduled).toHaveLength(1);

    act(() => scheduled[0].handler());

    expect(screen.queryByRole('button', { name: m.undoAction })).not.toBeInTheDocument();
  });

  it('revives an archived concept', async () => {
    governance.reviveGovernanceConcepts.mockResolvedValue(actionResult());
    const m = copy('en');
    renderWorkbench('en');
    await userEvent.click(await screen.findByRole('button', { name: startingWith(m.archivedQueue) }));

    await userEvent.click(screen.getByRole('button', { name: m.reviveButton }));

    expect(governance.reviveGovernanceConcepts).toHaveBeenCalledWith(['old-note'], 'agent-1');
    expect(await screen.findByText(m.reviveSuccess.replace('{name}', 'old-note'))).toBeInTheDocument();
  });

  it.each([
    ['rejects the request', () => governance.extendGovernanceConcepts.mockRejectedValue(new Error('network down'))],
    [
      'reports nothing changed',
      () => governance.extendGovernanceConcepts.mockResolvedValue(actionResult({ success: false })),
    ],
  ])('shows the localized failure when the server %s', async (_label, arrange) => {
    arrange();
    const m = copy('ja');
    renderWorkbench('ja');

    await userEvent.click((await screen.findAllByRole('button', { name: m.extendButton }))[0]);

    expect(await screen.findByText(m.actionError)).toBeInTheDocument();
    expect(screen.queryByText('English message from the server')).not.toBeInTheDocument();
    await waitFor(() => expect(governance.getGovernanceOverview).toHaveBeenCalledTimes(1));
  });
});
