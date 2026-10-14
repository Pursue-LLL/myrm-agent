/** @vitest-environment jsdom */
import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { KanbanTask } from '@/services/kanban';
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

function makeTask(taskId: string, title: string): KanbanTask {
  return {
    task_id: taskId,
    board_id: 'board-1',
    title,
    description: '',
    status: 'running',
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

interface HarnessProps {
  onDelete?: (taskId: string) => Promise<void>;
  onReclaim?: (taskId: string) => Promise<void>;
}

/** Mirrors how the board wires the hook: the tasks list is refreshed by the confirmed action itself. */
function Harness({ onDelete = async () => {}, onReclaim = async () => {} }: HarnessProps) {
  const [tasks, setTasks] = useState<KanbanTask[]>([TASK]);
  const { state, requestReclaim, requestDelete, dismiss } = useKanbanTaskActionConfirm(tasks);
  return (
    <>
      <button type="button" onClick={() => requestDelete('task-1')}>
        open-delete
      </button>
      <button type="button" onClick={() => requestReclaim('task-1')}>
        open-reclaim
      </button>
      <KanbanTaskActionConfirm
        state={state}
        onDismiss={dismiss}
        onReclaim={onReclaim}
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
function MenuHarness({ onDelete, onReclaim }: Required<HarnessProps>) {
  const { state, requestReclaim, requestDelete, dismiss } = useKanbanTaskActionConfirm([TASK]);
  return (
    <>
      <KanbanTaskCardActions
        task={TASK}
        onMove={vi.fn()}
        onSpecify={vi.fn()}
        onDecompose={vi.fn()}
        onDelete={requestDelete}
        onReclaim={requestReclaim}
      />
      <KanbanTaskActionConfirm state={state} onDismiss={dismiss} onReclaim={onReclaim} onDelete={onDelete} />
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

  it.each(Object.entries(locales))('%s: the old misnamed key is gone', (_locale, messages) => {
    expect(messages.kanban).not.toHaveProperty('reclaimConfirm');
  });
});
