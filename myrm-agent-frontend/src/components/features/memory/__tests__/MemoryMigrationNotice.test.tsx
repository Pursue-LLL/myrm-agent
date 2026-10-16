// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../locales/en.json';
import zh from '../../../../../locales/zh.json';

const executeReindex = vi.hoisted(() => vi.fn());
const checkOrphanCollections = vi.hoisted(() => vi.fn());

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

vi.mock('@/services/memory/reindex', () => ({
  getMemoryOrphanEstimate: vi.fn(),
  startMemoryReindex: vi.fn(),
  getMemoryReindexStatus: vi.fn(),
}));

import useRetrievalStore from '@/store/useRetrievalStore';
import MemoryMigrationNotice from '../settings/MemoryMigrationNotice';

function renderNotice(locale: 'en' | 'zh' = 'en', className?: string) {
  return render(
    <NextIntlClientProvider locale={locale} messages={locale === 'en' ? en : zh}>
      <MemoryMigrationNotice className={className} />
    </NextIntlClientProvider>,
  );
}

describe('MemoryMigrationNotice', () => {
  beforeEach(() => {
    executeReindex.mockReset();
    checkOrphanCollections.mockReset().mockResolvedValue(undefined);
    useRetrievalStore.setState({
      orphanCount: 0,
      orphanOldModels: [],
      reindexStatus: 'idle',
      reindexProgress: { done: 0, total: 0 },
      reindexResult: null,
      executeReindex,
      checkOrphanCollections,
    });
  });

  afterEach(cleanup);

  it('reads the leftover memories itself when it appears', () => {
    renderNotice();

    expect(checkOrphanCollections).toHaveBeenCalledTimes(1);
  });

  it('renders nothing while there is nothing to migrate', () => {
    const { container } = renderNotice();

    expect(container).toBeEmptyDOMElement();
  });

  it('reminds about leftover memories and starts the migration on request', () => {
    useRetrievalStore.setState({ orphanCount: 12 });
    renderNotice();

    expect(
      screen.getByText('12 memories are not used in replies until they are migrated to the new embedding model'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Migrate' }));

    expect(executeReindex).toHaveBeenCalledTimes(1);
  });

  it('lets the host page shape the notice', () => {
    useRetrievalStore.setState({ orphanCount: 1 });
    renderNotice('en', 'max-w-4xl');

    expect(screen.getByText(/1 memory is not used in replies/).closest('.max-w-4xl')).not.toBeNull();
  });

  it('dismisses the reminder', () => {
    useRetrievalStore.setState({ orphanCount: 12 });
    renderNotice();

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    expect(useRetrievalStore.getState().orphanCount).toBe(0);
  });

  it('shows live progress while the run is in flight, without offering to start again', () => {
    useRetrievalStore.setState({
      orphanCount: 12,
      reindexStatus: 'running',
      reindexProgress: { done: 40, total: 100 },
    });
    renderNotice();

    expect(screen.getByText('Migrating memories... 40 of 100')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40');
    expect(screen.queryByRole('button', { name: 'Migrate' })).not.toBeInTheDocument();
  });

  it('shows a plain migrating state before the total is known', () => {
    useRetrievalStore.setState({ orphanCount: 12, reindexStatus: 'running' });
    renderNotice();

    expect(screen.getByText('Migrating...')).toBeInTheDocument();
  });

  it('confirms a clean run with the number of migrated memories', () => {
    useRetrievalStore.setState({ reindexStatus: 'done', reindexResult: { migrated: 1, skipped: 0, failed: 0 } });
    renderNotice();

    expect(screen.getByText('1 memory migrated to the new model')).toBeInTheDocument();
  });

  it('says so when everything was already migrated', () => {
    useRetrievalStore.setState({ reindexStatus: 'done', reindexResult: { migrated: 0, skipped: 5, failed: 0 } });
    renderNotice();

    expect(screen.getByText('All memories are already on the new model')).toBeInTheDocument();
  });

  it('keeps the reminder with the failures and lets the user retry', () => {
    useRetrievalStore.setState({
      orphanCount: 3,
      reindexStatus: 'done',
      reindexResult: { migrated: 9, skipped: 0, failed: 3 },
    });
    renderNotice();

    expect(screen.getByText('9 migrated, 3 could not be migrated. Try again to retry them.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Migrate' }));

    expect(executeReindex).toHaveBeenCalledTimes(1);
  });

  it('offers a retry after an interrupted run', () => {
    useRetrievalStore.setState({ orphanCount: 12, reindexStatus: 'error' });
    renderNotice();

    expect(screen.getByText('Migration was interrupted. Try again to continue where it left off.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Migrate' })).toBeInTheDocument();
  });

  it('speaks the chosen language', () => {
    useRetrievalStore.setState({
      orphanCount: 3,
      reindexStatus: 'done',
      reindexResult: { migrated: 9, skipped: 0, failed: 3 },
    });
    renderNotice('zh');

    expect(screen.getByText('已迁移 9 条，3 条未能迁移，可再次尝试')).toBeInTheDocument();
  });
});
