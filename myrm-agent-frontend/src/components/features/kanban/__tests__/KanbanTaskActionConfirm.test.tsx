/** @vitest-environment jsdom */
import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { KanbanTask, TaskStatus } from '@/services/kanban';
import de from '../../../../../locales/de.json';
import en from '../../../../../locales/en.json';
import ja from '../../../../../locales/ja.json';
import ko from '../../../../../locales/ko.json';
import zhTW from '../../../../../locales/zh-TW.json';
import zh from '../../../../../locales/zh.json';
import KanbanTaskCardActions from '../KanbanTaskCardActions';
import { KanbanTaskActionConfirm, useKanbanTaskActionConfirm } from '../KanbanTaskActionConfirm';

// The global test setup replaces next-intl, so the real translator is loaded explicitly: shipped copy, real ICU.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const locales = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

vi.mock('next-intl', async () => {
  const actual = await vi.importActual<typeof import('next-intl')>('next-intl');
  const { default: messages } = await import('../../../../../locales/en.json');
  const translate = actual.createTranslator({ locale: 'en', messages, namespace: 'kanban' });
  return { useTranslations: () => translate };
});

function makeTask(taskId: string, title: string, status: TaskStatus = 'running'): KanbanTask {
  return {
    task_id: taskId,
    board_id: 'board-1',
    title,
    description: '',
    status,
    priority: 'normal',
    retry_count: 0,
    max_retries: 3,
    consecutive_failures: 0,
    result: '',
    error: '',
    metadata: {},
    extra_skill_ids: [],
    attachment_ids: [],
    attachments: [],
    dep_count: 0,
    children_total: 0,
    children_done: 0,
    comment_count: 0,
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
  };
}

const TASK = makeTask('task-1', 'Weekly report');
const FAILED_TASK = makeTask('task-1', 'Weekly report', 'failed');

interface HarnessProps {
  initialTasks?: KanbanTask[];
  onDelete?: (taskId: string) => Promise<void>;
  onReclaim?: (taskId: string) => Promise<void>;
  onRetry?: (taskId: string) => Promise<void>;
  onArchive?: (taskId: string) => Promise<void>;
  onMove?: (taskId: string, status: TaskStatus) => void;
}

/** Mirrors how the board wires the hook: the tasks list is refreshed by the confirmed action itself. */
function Harness({
  initialTasks = [TASK],
  onDelete = async () => {},
  onReclaim = async () => {},
  onRetry = async () => {},
  onArchive = async () => {},
  onMove = () => {},
}: HarnessProps) {
  const [tasks, setTasks] = useState<KanbanTask[]>(initialTasks);
  const { state, requestReclaim, requestDelete, requestMove, dismiss } = useKanbanTaskActionConfirm(tasks, onMove);
  return (
    <>
      <button type="button" onClick={() => requestDelete('task-1')}>
        open-delete
      </button>
      <button type="button" onClick={() => requestReclaim('task-1')}>
        open-reclaim
      </button>
      <button type="button" onClick={() => requestMove('task-1', 'ready')}>
        move-ready
      </button>
      <button type="button" onClick={() => requestMove('task-1', 'archived')}>
        move-archived
      </button>
      <button type="button" onClick={() => requestMove('task-1', 'completed')}>
        move-completed
      </button>
      <KanbanTaskActionConfirm
        state={state}
        onDismiss={dismiss}
        onReclaim={onReclaim}
        onRetry={onRetry}
        onArchive={onArchive}
        onDelete={async (taskId) => {
          await onDelete(taskId);
          setTasks([]);
        }}
      />
    </>
  );
}

const dialog = () => screen.findByRole('alertdialog');

describe('KanbanTaskActionConfirm', () => {
  it('renders nothing until an action is requested', () => {
    render(<Harness />);

    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('asks before deleting and spells out what deleting does', async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn(async () => {});
    render(<Harness onDelete={onDelete} />);

    await user.click(screen.getByRole('button', { name: 'open-delete' }));

    const confirm = await dialog();
    expect(confirm).toHaveTextContent('Delete this task?');
    expect(confirm).toHaveTextContent('"Weekly report"');
    expect(confirm).toHaveTextContent('deleted permanently');
    expect(confirm).toHaveTextContent('may start running automatically');
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith('task-1');
  });

  it('keeps naming the task while the confirmed delete is still running and the board has already dropped it', async () => {
    const user = userEvent.setup();
    let finishDelete: () => void = () => {};
    const onDelete = vi.fn(() => new Promise<void>((resolve) => (finishDelete = resolve)));
    render(<Harness onDelete={onDelete} />);

    await user.click(screen.getByRole('button', { name: 'open-delete' }));
    await user.click(screen.getByTestId('confirm-dialog-confirm'));

    expect(await dialog()).toHaveTextContent('"Weekly report"');
    finishDelete();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
  });

  it('asks before reclaiming and says the running agent is stopped', async () => {
    const user = userEvent.setup();
    const onReclaim = vi.fn(async () => {});
    render(<Harness onReclaim={onReclaim} />);

    await user.click(screen.getByRole('button', { name: 'open-reclaim' }));

    const confirm = await dialog();
    expect(confirm).toHaveTextContent('Reclaim Running Task');
    expect(confirm).toHaveTextContent('immediately stop the agent');
    expect(onReclaim).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(onReclaim).toHaveBeenCalledWith('task-1'));
  });

  it.each(['delete', 'reclaim'] as const)(
    'cancel closes the %s confirmation without acting and returns focus',
    async (kind) => {
      const user = userEvent.setup();
      const onDelete = vi.fn(async () => {});
      const onReclaim = vi.fn(async () => {});
      render(<Harness onDelete={onDelete} onReclaim={onReclaim} />);
      const opener = screen.getByRole('button', { name: `open-${kind}` });

      await user.click(opener);
      await dialog();
      await user.click(screen.getByTestId('confirm-dialog-cancel'));

      await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
      expect(onDelete).not.toHaveBeenCalled();
      expect(onReclaim).not.toHaveBeenCalled();
      expect(opener).toHaveFocus();
    },
  );

  it.each(['delete', 'reclaim'] as const)(
    'Escape closes the %s confirmation without acting and returns focus',
    async (kind) => {
      const user = userEvent.setup();
      const onDelete = vi.fn(async () => {});
      const onReclaim = vi.fn(async () => {});
      render(<Harness onDelete={onDelete} onReclaim={onReclaim} />);
      const opener = screen.getByRole('button', { name: `open-${kind}` });

      await user.click(opener);
      await dialog();
      await user.keyboard('{Escape}');

      await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
      expect(onDelete).not.toHaveBeenCalled();
      expect(onReclaim).not.toHaveBeenCalled();
      expect(opener).toHaveFocus();
    },
  );

  it('can be opened again after it was dismissed', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'open-reclaim' }));
    await dialog();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    await user.click(screen.getByRole('button', { name: 'open-delete' }));

    expect(await dialog()).toHaveTextContent('Delete this task?');
  });
});

/** The board's real entry point: a card menu item selects the action, the menu closes, the confirmation takes over. */
function MenuHarness({
  task = TASK,
  onDelete = async () => {},
  onReclaim = async () => {},
  onRetry = async () => {},
  onArchive = async () => {},
  onMove = () => {},
}: Omit<HarnessProps, 'initialTasks'> & { task?: KanbanTask }) {
  const { state, requestReclaim, requestDelete, requestMove, dismiss } = useKanbanTaskActionConfirm([task], onMove);
  return (
    <>
      <KanbanTaskCardActions
        task={task}
        onMove={requestMove}
        onSpecify={vi.fn()}
        onDecompose={vi.fn()}
        onDelete={requestDelete}
        onReclaim={requestReclaim}
      />
      <KanbanTaskActionConfirm
        state={state}
        onDismiss={dismiss}
        onReclaim={onReclaim}
        onDelete={onDelete}
        onRetry={onRetry}
        onArchive={onArchive}
      />
    </>
  );
}

describe('KanbanTaskActionConfirm from the card menu', () => {
  const trigger = () => screen.getByRole('button', { name: 'Task actions' });

  it.each([
    ['Delete', 'Delete this task?'],
    ['Reclaim', 'Reclaim Running Task'],
  ])('%s: selecting the menu item only opens the confirmation', async (item, heading) => {
    const user = userEvent.setup();
    const onDelete = vi.fn(async () => {});
    const onReclaim = vi.fn(async () => {});
    render(<MenuHarness onDelete={onDelete} onReclaim={onReclaim} />);

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: item }));

    expect(await dialog()).toHaveTextContent(heading);
    expect(onDelete).not.toHaveBeenCalled();
    expect(onReclaim).not.toHaveBeenCalled();
  });

  it.each(['Delete', 'Reclaim'])('%s: Escape returns focus to the card menu button, not the page', async (item) => {
    const user = userEvent.setup();
    render(<MenuHarness onDelete={async () => {}} onReclaim={async () => {}} />);

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: item }));
    await dialog();
    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(trigger()).toHaveFocus();
  });
});

describe('KanbanTaskActionConfirm move gate', () => {
  it('failed → ready asks before retrying and says the task runs again', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn(async () => {});
    const onMove = vi.fn();
    render(<Harness initialTasks={[FAILED_TASK]} onRetry={onRetry} onMove={onMove} />);

    await user.click(screen.getByRole('button', { name: 'move-ready' }));

    const confirm = await dialog();
    expect(confirm).toHaveTextContent('Retry this task?');
    expect(confirm).toHaveTextContent('runs again');
    expect(confirm).toHaveTextContent('model quota');
    expect(onRetry).not.toHaveBeenCalled();
    expect(onMove).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(onRetry).toHaveBeenCalledWith('task-1'));
    expect(onMove).not.toHaveBeenCalled();
  });

  it('archiving asks first, names the task, and only moves after confirmation', async () => {
    const user = userEvent.setup();
    const onArchive = vi.fn(async () => {});
    const onMove = vi.fn();
    render(<Harness initialTasks={[FAILED_TASK]} onArchive={onArchive} onMove={onMove} />);

    await user.click(screen.getByRole('button', { name: 'move-archived' }));

    const confirm = await dialog();
    expect(confirm).toHaveTextContent('Archive this task?');
    expect(confirm).toHaveTextContent('"Weekly report"');
    expect(confirm).toHaveTextContent('cannot be restored');
    expect(onArchive).not.toHaveBeenCalled();
    expect(onMove).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(onArchive).toHaveBeenCalledWith('task-1'));
    expect(onMove).not.toHaveBeenCalled();
  });

  it('an ordinary move goes straight through with no dialog', async () => {
    const user = userEvent.setup();
    const onMove = vi.fn();
    render(<Harness onMove={onMove} />);

    await user.click(screen.getByRole('button', { name: 'move-completed' }));

    expect(onMove).toHaveBeenCalledWith('task-1', 'completed');
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it.each(['move-ready', 'move-archived'])('%s: cancelling runs nothing and returns focus', async (opener) => {
    const user = userEvent.setup();
    const onRetry = vi.fn(async () => {});
    const onArchive = vi.fn(async () => {});
    const onMove = vi.fn();
    render(<Harness initialTasks={[FAILED_TASK]} onRetry={onRetry} onArchive={onArchive} onMove={onMove} />);
    const trigger = screen.getByRole('button', { name: opener });

    await user.click(trigger);
    await dialog();
    await user.click(screen.getByTestId('confirm-dialog-cancel'));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(onRetry).not.toHaveBeenCalled();
    expect(onArchive).not.toHaveBeenCalled();
    expect(onMove).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();
  });
});

describe('KanbanTaskActionConfirm move gate from the card menu', () => {
  const trigger = () => screen.getByRole('button', { name: 'Task actions' });

  it('a failed card offers Retry instead of Move to Ready, and Retry opens the confirmation', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn(async () => {});
    const onMove = vi.fn();
    render(<MenuHarness task={FAILED_TASK} onRetry={onRetry} onMove={onMove} />);

    await user.click(trigger());
    expect(screen.queryByRole('menuitem', { name: 'Move to Ready' })).toBeNull();
    await user.click(screen.getByRole('menuitem', { name: 'Retry' }));

    expect(await dialog()).toHaveTextContent('Retry this task?');
    expect(onRetry).not.toHaveBeenCalled();
    expect(onMove).not.toHaveBeenCalled();
  });

  it('Archive opens the confirmation instead of archiving right away', async () => {
    const user = userEvent.setup();
    const onArchive = vi.fn(async () => {});
    const onMove = vi.fn();
    render(<MenuHarness task={FAILED_TASK} onArchive={onArchive} onMove={onMove} />);

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'Archive' }));

    expect(await dialog()).toHaveTextContent('Archive this task?');
    expect(onArchive).not.toHaveBeenCalled();
    expect(onMove).not.toHaveBeenCalled();
  });

  it('an ordinary move item acts immediately', async () => {
    const user = userEvent.setup();
    const onMove = vi.fn();
    render(<MenuHarness task={makeTask('task-1', 'Weekly report', 'ready')} onMove={onMove} />);

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'Start' }));

    expect(onMove).toHaveBeenCalledWith('task-1', 'running');
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});

describe('kanban confirmation copy in every locale', () => {
  const title = 'Q3 {plan} <draft>';

  it.each(Object.entries(locales))(
    '%s: delete copy names the task and leaves no raw placeholder',
    (locale, messages) => {
      const t = createTranslator({ locale, messages, namespace: 'kanban' });

      const description = t('deleteConfirmDesc', { title });

      expect(description).toContain(title);
      expect(description).not.toContain('{title}');
      expect(description.split('\n')).toHaveLength(2);
      for (const key of [
        'deleteConfirmTitle',
        'deleteAction',
        'reclaimTitle',
        'reclaimDesc',
        'reclaimAction',
      ] as const) {
        expect(t(key).trim()).not.toBe('');
        expect(t(key)).not.toContain('kanban.');
      }
    },
  );

  it.each(Object.entries(locales))(
    '%s: retry and archive copy resolves with no raw placeholder',
    (locale, messages) => {
      const t = createTranslator({ locale, messages, namespace: 'kanban' });

      const archiveDescription = t('archiveConfirmDesc', { title });
      expect(archiveDescription).toContain(title);
      expect(archiveDescription).not.toContain('{title}');
      expect(archiveDescription.split('\n')).toHaveLength(2);

      const bulk = t('bulkArchiveConfirm', { count: 3 });
      expect(bulk).toContain('3');
      expect(bulk).not.toContain('{count}');

      for (const key of [
        'retryAction',
        'retryTitle',
        'retryDesc',
        'retrySuccess',
        'retryError',
        'moveBlocked',
        'archiveConfirmTitle',
        'moveTo.archived',
      ] as const) {
        expect(t(key).trim()).not.toBe('');
        expect(t(key)).not.toContain('kanban.');
      }
    },
  );

  it.each(Object.entries(locales))('%s: the old misnamed key is gone', (_locale, messages) => {
    expect(messages.kanban).not.toHaveProperty('reclaimConfirm');
  });
});
