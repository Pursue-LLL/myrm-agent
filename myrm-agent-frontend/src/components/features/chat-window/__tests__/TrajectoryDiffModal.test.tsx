import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatItem, SessionTrajectoryResponse } from '@/services/chat';
import { deferred } from '@/test-utils/deferred';

import TrajectoryDiffModal from '../TrajectoryDiffModal';
import { step, trajectory, turn } from './trajectoryKit';

const hoisted = vi.hoisted(() => ({ trajectory: vi.fn(), history: vi.fn() }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  getSessionTrajectory: (...args: unknown[]) => hoisted.trajectory(...args),
  getChatHistory: (...args: unknown[]) => hoisted.history(...args),
}));

const chat = (id: string, title: string): ChatItem => ({
  id,
  title,
  firstMessage: '',
  lastMessage: '',
  actionMode: 'agent',
  source: 'web',
  updatedAt: new Date('2026-03-02T12:00:00Z'),
  createdAt: new Date('2026-03-01T12:00:00Z'),
});

const sessions = {
  current: trajectory('current-session-id', 'Refactor auth', [
    turn('t1', 'fix the login bug', [
      step('read_file', { path: 'a.ts' }, { duration_ms: 1234.6, tokens_used: 34 }),
      step('grep', { pattern: 'login' }),
    ]),
    turn('t2', 'now add tests', [step('edit_file', { path: 'a.ts' }), step('run_tests', { suite: 'auth' })]),
  ]),
  alike: trajectory('other-1', 'Same path', [
    turn('t1', 'fix the login bug', [step('read_file', { path: 'a.ts' }), step('grep', { pattern: 'login' })]),
    turn('t2', 'now add tests', [step('edit_file', { path: 'a.ts' }), step('run_tests', { suite: 'auth' })]),
  ]),
  diverging: trajectory('other-2', 'Other path', [
    turn('t1', 'fix the login bug', [step('read_file', { path: 'a.ts' }), step('grep', { pattern: 'login' })]),
    turn('t2', 'now add tests', [step('edit_file', { path: 'a.ts' }), step('build', {})]),
  ]),
  shorter: trajectory('other-3', null, [turn('t1', 'fix the login bug', [step('read_file', { path: 'a.ts' })])]),
};
const byId: Record<string, SessionTrajectoryResponse> = {
  'current-session-id': sessions.current,
  'other-1': sessions.alike,
  'other-2': sessions.diverging,
  'other-3': sessions.shorter,
};

function renderModal(props: { open?: boolean } = {}) {
  const onClose = vi.fn();
  const view = render(
    <TrajectoryDiffModal open={props.open ?? true} currentSessionId="current-session-id" onClose={onClose} />,
  );
  return { onClose, ...view };
}

const picker = () => screen.getByLabelText(/Compare with Session/) as HTMLSelectElement;
const pick = (id: string) => fireEvent.change(picker(), { target: { value: id } });
const divergent = () =>
  Array.from(document.querySelectorAll('[data-divergent]')).map(
    (card) => card.querySelector('span.font-mono')?.textContent,
  );
const banner = () => screen.queryByText(/Execution divergence detected/);
const toolNames = () =>
  Array.from(document.querySelectorAll('div[class*="rounded-lg"] > div > div > span.font-mono')).map(
    (e) => e.textContent,
  );

beforeEach(() => {
  vi.resetAllMocks();
  hoisted.trajectory.mockImplementation(async (id: string) => byId[id]);
  hoisted.history.mockResolvedValue({
    items: [
      chat('current-session-id', 'Refactor auth'),
      chat('other-1', 'Same path'),
      chat('other-2', 'Other path'),
      chat('other-3', ''),
    ],
    pagination: { page: 1, pageSize: 30, total: 4, totalPages: 1, hasNext: false, hasPrev: false },
  });
});

describe('TrajectoryDiffModal reading', () => {
  it('reads nothing while closed', () => {
    renderModal({ open: false });

    expect(hoisted.trajectory).not.toHaveBeenCalled();
    expect(hoisted.history).not.toHaveBeenCalled();
  });

  it('shows the current session turn by turn with its totals', async () => {
    renderModal();

    expect(await screen.findByText('Session A (current: Refactor auth)')).toBeInTheDocument();
    expect(screen.getByText('4 calls | 34 tokens')).toBeInTheDocument();
    expect(screen.getByText('Prompt: fix the login bug')).toBeInTheDocument();
    expect(screen.getByText('Prompt: now add tests')).toBeInTheDocument();
    expect(toolNames()).toEqual(['read_file', 'grep', 'edit_file', 'run_tests']);
    expect(screen.getByText('1235ms')).toBeInTheDocument();
    expect(screen.getAllByText('34 tok')).toHaveLength(1);
    expect(screen.queryByText(/^0 tok$/)).toBeNull();
    expect(hoisted.trajectory).toHaveBeenCalledExactlyOnceWith('current-session-id');
    expect(hoisted.history).toHaveBeenCalledExactlyOnceWith(1, 30);
  });

  it('says it is loading until the trajectory arrives', async () => {
    const pending = deferred<SessionTrajectoryResponse>();
    hoisted.trajectory.mockReturnValue(pending.promise);
    renderModal();

    expect(screen.getByRole('status')).toHaveTextContent('Loading trajectory...');
    expect(screen.getByText('Session A (current: current-)')).toBeInTheDocument();

    await act(async () => pending.resolve(sessions.current));

    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByText('Session A (current: Refactor auth)')).toBeInTheDocument();
  });

  it('offers the other recent sessions, by title or else by the start of their id', async () => {
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');

    const options = within(picker()).getAllByRole('option');

    expect(options.map((option) => option.getAttribute('value'))).toEqual(['', 'other-1', 'other-2', 'other-3']);
    expect(options[0]).toHaveTextContent('Select a historical session to compare...');
    expect(options[1]).toHaveTextContent(/^Same path \(/);
    expect(options[3]).toHaveTextContent(/^other-3 \(/);
  });

  it('keeps a placeholder for session B until one is picked, then shows it', async () => {
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');
    expect(screen.getByText('Session B (none)')).toBeInTheDocument();
    expect(screen.getByText('Select a session above to start side-by-side trajectory comparison')).toBeInTheDocument();

    pick('other-2');

    expect(await screen.findByText('Session B (Other path)')).toBeInTheDocument();
    expect(screen.queryByText(/Select a session above/)).toBeNull();
    expect(toolNames()).toEqual([
      'read_file',
      'grep',
      'edit_file',
      'run_tests',
      'read_file',
      'grep',
      'edit_file',
      'build',
    ]);
  });

  it('falls back to the start of the id for a session without a title', async () => {
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');

    pick('other-3');

    expect(await screen.findByText('Session B (other-3)')).toBeInTheDocument();
  });
});

describe('TrajectoryDiffModal divergence', () => {
  async function compareWith(id: keyof typeof byId) {
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');
    pick(id);
    await vi.waitFor(() => expect(hoisted.trajectory).toHaveBeenCalledWith(id));
    await screen.findByText(`Session B (${byId[id].title ?? id})`);
  }

  it('marks the diverging step in its own turn on both sides and names it by its position over all turns', async () => {
    await compareWith('other-2');

    expect(screen.getByText('Execution divergence detected at Step #4')).toBeInTheDocument();
    expect(divergent()).toEqual(['run_tests', 'build']);
  });

  it('says nothing when the sessions ran alike', async () => {
    await compareWith('other-1');

    expect(banner()).toBeNull();
    expect(divergent()).toEqual([]);
  });

  it('marks the first step only the longer session has', async () => {
    await compareWith('other-3');

    expect(screen.getByText('Execution divergence detected at Step #2')).toBeInTheDocument();
    expect(divergent()).toEqual(['grep']);
  });

  it('clears the mark when the comparison is dropped again', async () => {
    await compareWith('other-2');

    pick('');

    await vi.waitFor(() => expect(banner()).toBeNull());
    expect(divergent()).toEqual([]);
    expect(screen.getByText('Session B (none)')).toBeInTheDocument();
  });
});

describe('TrajectoryDiffModal when answers arrive out of order or fail', () => {
  const failing = () => Promise.reject(new Error('boom'));

  it('shows the session picked last even if an earlier pick answers later', async () => {
    const first = deferred<SessionTrajectoryResponse>();
    const second = deferred<SessionTrajectoryResponse>();
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');
    hoisted.trajectory.mockImplementation((id: string) => (id === 'other-1' ? first.promise : second.promise));

    pick('other-1');
    pick('other-2');
    await act(async () => second.resolve(sessions.diverging));
    await act(async () => first.resolve(sessions.alike));

    expect(screen.getByText('Session B (Other path)')).toBeInTheDocument();
    expect(screen.queryByText('Session B (Same path)')).toBeNull();
    expect(divergent()).toEqual(['run_tests', 'build']);
  });

  it('does not bring a session back that was dropped while it was loading', async () => {
    const late = deferred<SessionTrajectoryResponse>();
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');
    hoisted.trajectory.mockReturnValue(late.promise);

    pick('other-2');
    pick('');
    await act(async () => late.resolve(sessions.diverging));

    expect(screen.getByText('Session B (none)')).toBeInTheDocument();
    expect(screen.getByText(/Select a session above/)).toBeInTheDocument();
    expect(banner()).toBeNull();
  });

  it('ignores a read that fails after the session picked next is already shown', async () => {
    const late = deferred<SessionTrajectoryResponse>();
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');
    hoisted.trajectory.mockImplementation((id: string) =>
      id === 'other-1' ? late.promise : Promise.resolve(byId[id]),
    );

    pick('other-1');
    pick('other-2');
    await screen.findByText('Session B (Other path)');
    await act(async () => late.reject(new Error('boom')));

    expect(screen.getByText('Session B (Other path)')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(divergent()).toEqual(['run_tests', 'build']);
  });

  it('does not show the previous pick while the next one is loading', async () => {
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');
    pick('other-2');
    await screen.findByText('Session B (Other path)');
    hoisted.trajectory.mockReturnValue(new Promise(() => undefined));

    pick('other-1');

    expect(screen.getByRole('status')).toHaveTextContent('Loading trajectory...');
    expect(screen.queryByText('Session B (Other path)')).toBeNull();
    expect(banner()).toBeNull();
  });

  it('says so when the current session cannot be read, and still offers to compare', async () => {
    hoisted.trajectory.mockImplementation((id: string) =>
      id === 'current-session-id' ? failing() : Promise.resolve(byId[id]),
    );
    renderModal();

    expect(await screen.findByRole('alert')).toHaveTextContent("Could not load this session's trajectory.");
    pick('other-1');

    expect(await screen.findByText('Session B (Same path)')).toBeInTheDocument();
    expect(banner()).toBeNull();
  });

  it('says so when the picked session cannot be read, instead of asking to pick one', async () => {
    renderModal();
    await screen.findByText('Session A (current: Refactor auth)');
    hoisted.trajectory.mockImplementation(failing);

    pick('other-2');

    expect(await screen.findByRole('alert')).toHaveTextContent("Could not load this session's trajectory.");
    expect(screen.queryByText(/Select a session above/)).toBeNull();
    expect(screen.getByText('Session B (other-2)')).toBeInTheDocument();
  });

  it('says so when the list of sessions cannot be read', async () => {
    hoisted.history.mockRejectedValue(new Error('offline'));
    renderModal();

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the session list.');
    expect(within(picker()).getAllByRole('option')).toHaveLength(1);
    expect(await screen.findByText('Session A (current: Refactor auth)')).toBeInTheDocument();
  });
});

describe('TrajectoryDiffModal closing', () => {
  it('asks to close from Escape and from the close button, not otherwise', async () => {
    const { onClose } = renderModal();
    await screen.findByText('Session A (current: Refactor auth)');
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
