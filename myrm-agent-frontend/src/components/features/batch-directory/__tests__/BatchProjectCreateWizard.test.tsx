/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BatchDirectoriesPage from '@/app/batch-directories/page';
import type { BatchProjectDetail } from '@/services/batch-directory';
import {
  browseDirectories,
  click,
  deferred,
  listBoards,
  mkDetail,
  resetBatchMocks,
  router,
  serviceMocks,
  settle,
  toast,
  typeInto,
} from './batchTestKit';

vi.mock('next-intl', () => import('./batchTestKit').then((m) => ({ useTranslations: () => m.t })));
vi.mock('next/navigation', () => import('./batchTestKit').then((m) => ({ useRouter: () => m.router })));
vi.mock('next/link', () => import('./batchTestKit').then((m) => ({ default: m.Link })));
vi.mock('@/hooks/shared/useToast', () => import('./batchTestKit').then((m) => ({ toast: m.toast })));
vi.mock('@/services/batch-directory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/batch-directory')>()),
  ...(await import('./batchTestKit')).serviceMocks,
}));
vi.mock('@/services/kanban', () => import('./batchTestKit').then((m) => ({ listBoards: m.listBoards })));
vi.mock('@/services/chat', () => import('./batchTestKit').then((m) => ({ browseDirectories: m.browseDirectories })));
vi.mock('@/services/riskHeldToast', () =>
  import('./batchTestKit').then((m) => ({ isRiskHeldError: m.isRiskHeldError })),
);

const LISTINGS: Record<string, { current: string; entries: { name: string; path: string }[] }> = {
  '~': {
    current: '~',
    entries: [
      { name: 'docs', path: '/home/u/docs' },
      { name: 'src', path: '/home/u/src' },
    ],
  },
  '/home/u/docs': { current: '/home/u/docs', entries: [] },
  '/home/u/src': { current: '/home/u/src', entries: [{ name: 'lib', path: '/home/u/src/lib' }] },
  '/home/u': { current: '/home/u', entries: [{ name: 'docs', path: '/home/u/docs' }] },
  '/home': { current: '/home', entries: [] },
};

const headerButton = () => screen.getAllByRole('button', { name: 'createButton' })[0];
const submitButton = () => screen.getAllByRole('button', { name: 'createButton' })[1];
const entryCheckbox = (name: string) => screen.getByRole('checkbox', { name: new RegExp(name) });
const browseInto = (index: number) => screen.getAllByRole('button', { name: 'browseInto' })[index];

async function openWizard() {
  serviceMocks.listBatchProjects.mockResolvedValue([]);
  listBoards.mockResolvedValue({
    items: [
      { board_id: 'b1', name: 'Board One' },
      { board_id: 'b2', name: 'Board Two' },
    ],
  });
  browseDirectories.mockImplementation(async (path: string) => LISTINGS[path]);
  render(<BatchDirectoriesPage />);
  await settle();
  await click(headerButton());
}

async function fillRequired() {
  await typeInto(screen.getByLabelText('nameLabel'), '  My batch  ');
  await typeInto(screen.getByLabelText('promptLabel'), '  Do it  ');
  await click(entryCheckbox('docs'));
}

beforeEach(resetBatchMocks);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('create wizard', () => {
  it('opens from the home directory, replaces the stat cards, and toggles closed', async () => {
    await openWizard();
    expect(browseDirectories).toHaveBeenCalledWith('~');
    expect(screen.getByText('createTitle')).toBeInTheDocument();
    expect(screen.queryByText('statProjects')).toBeNull();
    expect(screen.getByText('docs')).toBeInTheDocument();

    await click(headerButton());
    expect(screen.queryByText('createTitle')).toBeNull();
    expect(screen.getByText('statProjects')).toBeInTheDocument();
  });

  it('validates name, prompt and directories in order without calling the API', async () => {
    await openWizard();
    await click(submitButton());
    expect(toast.error).toHaveBeenLastCalledWith('nameRequired');
    await typeInto(screen.getByLabelText('nameLabel'), ' x ');
    await click(submitButton());
    expect(toast.error).toHaveBeenLastCalledWith('promptRequired');
    await typeInto(screen.getByLabelText('promptLabel'), ' y ');
    await click(submitButton());
    expect(toast.error).toHaveBeenLastCalledWith('dirsRequired');
    expect(serviceMocks.createBatchProject).not.toHaveBeenCalled();
  });

  it('submits a trimmed payload, then resets the form and navigates to the new project', async () => {
    await openWizard();
    await fillRequired();
    await typeInto(screen.getByLabelText('boardLabel'), 'b2');
    await typeInto(screen.getByLabelText('concurrencyLabel'), '0');
    await typeInto(screen.getByLabelText('artifactPatternsLabel'), ' *.md , ,out/*.csv ');
    await click(screen.getByLabelText('notifyLabel'));
    await click(screen.getByLabelText('approvalLabel'));
    serviceMocks.createBatchProject.mockResolvedValue(mkDetail({ project_id: 'new-1', name: 'My batch' }));

    await click(submitButton());

    expect(serviceMocks.createBatchProject).toHaveBeenCalledWith({
      name: 'My batch',
      prompt: 'Do it',
      directories: ['/home/u/docs'],
      board_id: 'b2',
      concurrency: 3,
      notify_enabled: false,
      require_approval: true,
      artifact_patterns: ['*.md', 'out/*.csv'],
    });
    expect(toast.success).toHaveBeenCalledWith('createSuccess{"name":"My batch"}');
    expect(serviceMocks.listBatchProjects).toHaveBeenCalledTimes(2);
    expect(router.push).toHaveBeenCalledWith('/batch-directories/new-1');
    expect(screen.queryByText('createTitle')).toBeNull();

    await click(headerButton());
    expect(screen.getByLabelText('nameLabel')).toHaveValue('');
    expect(screen.getByLabelText('notifyLabel')).toBeChecked();
    expect(screen.queryByText(/dirsSelectedCount/)).toBeNull();
  });

  it('uses defaults for optional fields', async () => {
    await openWizard();
    await fillRequired();
    serviceMocks.createBatchProject.mockResolvedValue(mkDetail());
    await click(submitButton());
    expect(serviceMocks.createBatchProject).toHaveBeenCalledWith({
      name: 'My batch',
      prompt: 'Do it',
      directories: ['/home/u/docs'],
      board_id: null,
      concurrency: 3,
      notify_enabled: true,
      require_approval: false,
      artifact_patterns: [],
    });
  });

  it('keeps the form and selection when hidden and reopened, but restarts browsing at home', async () => {
    await openWizard();
    await typeInto(screen.getByLabelText('nameLabel'), 'Keep me');
    await click(entryCheckbox('docs'));
    await click(browseInto(1));
    expect(screen.getByText('/home/u/src')).toBeInTheDocument();

    await click(screen.getByRole('button', { name: 'cancelButton' }));
    await click(headerButton());

    expect(screen.getByLabelText('nameLabel')).toHaveValue('Keep me');
    expect(screen.getByText('dirsSelectedCount{"count":1}')).toBeInTheDocument();
    expect(browseDirectories).toHaveBeenLastCalledWith('~');
  });

  it('reports create failures, keeps the form, and stays silent for held prompts', async () => {
    await openWizard();
    await fillRequired();

    serviceMocks.createBatchProject.mockRejectedValueOnce(new Error('boom'));
    await click(submitButton());
    expect(toast.error).toHaveBeenLastCalledWith('boom');

    serviceMocks.createBatchProject.mockRejectedValueOnce('weird');
    await click(submitButton());
    expect(toast.error).toHaveBeenLastCalledWith('createError');

    toast.error.mockClear();
    serviceMocks.createBatchProject.mockRejectedValueOnce({ riskHeld: true });
    await click(submitButton());
    expect(toast.error).not.toHaveBeenCalled();

    expect(screen.getByLabelText('nameLabel')).toHaveValue('  My batch  ');
    expect(submitButton()).toBeEnabled();
    expect(router.push).not.toHaveBeenCalled();
  });

  it('disables both create buttons while the request is pending', async () => {
    await openWizard();
    await fillRequired();
    const pending = deferred<BatchProjectDetail>();
    serviceMocks.createBatchProject.mockReturnValue(pending.promise);
    await click(submitButton());
    expect(submitButton()).toBeDisabled();
    expect(headerButton()).toBeDisabled();

    pending.resolve(mkDetail());
    await settle();
    expect(router.push).toHaveBeenCalled();
  });
});

describe('directory picker', () => {
  it('selects and deselects a directory with a single click on its name', async () => {
    await openWizard();
    await click(screen.getByText('docs'));
    expect(entryCheckbox('docs')).toBeChecked();
    expect(screen.getByText('dirsSelectedCount{"count":1}')).toBeInTheDocument();

    await click(screen.getByText('docs'));
    expect(entryCheckbox('docs')).not.toBeChecked();
    expect(screen.queryByText(/dirsSelectedCount/)).toBeNull();
  });

  it('toggles once from the checkbox itself and from the keyboard', async () => {
    const user = userEvent.setup();
    await openWizard();
    await user.click(entryCheckbox('docs'));
    expect(entryCheckbox('docs')).toBeChecked();

    entryCheckbox('docs').focus();
    await user.keyboard(' ');
    expect(entryCheckbox('docs')).not.toBeChecked();
  });

  it('enters a directory without toggling its selection and keeps selections across folders', async () => {
    await openWizard();
    await click(entryCheckbox('docs'));
    await click(browseInto(1));

    expect(browseDirectories).toHaveBeenLastCalledWith('/home/u/src');
    expect(screen.getByText('lib')).toBeInTheDocument();
    expect(screen.getByText('dirsSelectedCount{"count":1}')).toBeInTheDocument();

    await click(screen.getByText('lib'));
    expect(screen.getByText('dirsSelectedCount{"count":2}')).toBeInTheDocument();
  });

  it('goes up one level, falls back to home at the top, and refreshes the current folder', async () => {
    await openWizard();
    expect(screen.queryByRole('button', { name: 'browseUp' })).toBeNull();

    await click(browseInto(1));
    await click(screen.getByRole('button', { name: 'browseUp' }));
    expect(browseDirectories).toHaveBeenLastCalledWith('/home/u');

    await click(screen.getByRole('button', { name: 'browseUp' }));
    expect(browseDirectories).toHaveBeenLastCalledWith('/home');

    await click(screen.getByRole('button', { name: 'browseUp' }));
    expect(browseDirectories).toHaveBeenLastCalledWith('~');

    browseDirectories.mockClear();
    await click(document.querySelector('svg.lucide-refresh-cw')?.closest('button') as HTMLElement);
    expect(browseDirectories).toHaveBeenCalledWith('~');
  });

  it('shows the empty hint and reports browse failures', async () => {
    await openWizard();
    browseDirectories.mockRejectedValueOnce(new Error('denied'));
    await click(browseInto(1));
    expect(toast.error).toHaveBeenCalledWith('browseError');
    expect(screen.getByText('docs')).toBeInTheDocument();

    await click(browseInto(0));
    expect(screen.getByText('browseEmpty')).toBeInTheDocument();
  });
});
