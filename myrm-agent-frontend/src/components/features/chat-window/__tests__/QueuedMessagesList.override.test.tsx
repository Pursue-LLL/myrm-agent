/**
 * Unit tests for QueuedMessagesList: capability override badge, attachment badge, status banner and editing.
 */

import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { QueuedMessagesList } from '../QueuedMessagesList';
import type { QueuedMessage } from '@/store/chat/useMessageQueueStore';

const CHAT_T: Record<string, string> = {
  'queue.queued': 'Queued #{index}/{total}:',
  'queue.edit': 'Edit',
  'queue.cancel': 'Cancel',
  'queue.saveEdit': 'Save',
  'queue.cancelEdit': 'Cancel edit',
  'queue.editHint': 'Enter to save',
  'queue.reorder': 'Reorder',
  'queue.listLabel': 'Queued messages',
  'queue.attachments': '{count} attachments',
  'queue.pausedStopped': 'Queue paused',
  'queue.stuck': 'Could not send',
  'queue.resume': 'Resume',
  'queue.retry': 'Retry',
  overrideSkillsShort: '{skills} skills',
  overrideMcpShort: '{mcps} MCP',
};

const stableT = (key: string, params?: Record<string, number | string>) => {
  let template = CHAT_T[key] || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      template = template.replace(`{${k}}`, String(v));
    }
  }
  return template;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const message = (id: string, text: string, overrides: Partial<QueuedMessage> = {}): QueuedMessage => ({
  id,
  text,
  files: [],
  timestamp: 1,
  ...overrides,
});

function renderList(overrides: Partial<React.ComponentProps<typeof QueuedMessagesList>> = {}) {
  const props: React.ComponentProps<typeof QueuedMessagesList> = {
    queue: [message('q-1', 'first task'), message('q-2', 'second task')],
    pausedReason: null,
    editingId: null,
    setEditingId: vi.fn(),
    editMessage: vi.fn(),
    removeMessage: vi.fn(),
    reorder: vi.fn(),
    resume: vi.fn(),
    ...overrides,
  };
  const view = render(<QueuedMessagesList {...props} />);
  return { props, ...view };
}

describe('QueuedMessagesList override badge', () => {
  it('renders override badge when queued message has turnCapabilitySelection', () => {
    renderList({
      queue: [
        message('q-1', 'Task with override', {
          turnCapabilitySelection: { skillIds: ['skill-1', 'skill-2'], mcpNames: ['mcp-1'] },
        }),
        message('q-2', 'Normal queued task', { turnCapabilitySelection: null }),
      ],
    });

    expect(screen.getByText('2 skills · 1 MCP')).toBeInTheDocument();
    expect(screen.getByText('Task with override')).toBeInTheDocument();
    expect(screen.getByText('Normal queued task')).toBeInTheDocument();
  });
});

describe('QueuedMessagesList', () => {
  it('renders nothing for an empty queue', () => {
    const { container } = renderList({ queue: [] });

    expect(container).toBeEmptyDOMElement();
  });

  it('labels the list and numbers its entries', () => {
    renderList();

    expect(screen.getByRole('list', { name: 'Queued messages' })).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText('Queued #1/2:')).toBeInTheDocument();
    expect(screen.getByText('Queued #2/2:')).toBeInTheDocument();
  });

  it('shows how many attachments a queued message carries', () => {
    renderList({ queue: [message('q-1', 'see files', { files: [{ id: 'f1' }, { id: 'f2' }] as never })] });

    expect(screen.getByText('2 attachments')).toBeInTheDocument();
  });

  it('removes a message through its cancel action', async () => {
    const { props } = renderList();

    await userEvent.click(screen.getAllByRole('button', { name: 'Cancel' })[0]);

    expect(props.removeMessage).toHaveBeenCalledWith('q-1');
  });

  describe('status banner', () => {
    it('stays hidden while the queue drains on its own', () => {
      renderList();

      expect(screen.queryByText('Queue paused')).not.toBeInTheDocument();
      expect(screen.queryByText('Could not send')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Resume|Retry/ })).not.toBeInTheDocument();
    });

    it('explains a stopped queue and resumes it', async () => {
      const { props } = renderList({ pausedReason: 'stopped' });

      expect(screen.getByText('Queue paused')).toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: /Resume/ }));

      expect(props.resume).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when sending got stuck', async () => {
      const { props } = renderList({ pausedReason: 'stuck' });

      expect(screen.getByText('Could not send')).toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: /Retry/ }));

      expect(props.resume).toHaveBeenCalledTimes(1);
    });
  });

  describe('editing', () => {
    it('locks the message while it is edited', async () => {
      const { props } = renderList();

      await userEvent.click(screen.getAllByRole('button', { name: 'Edit' })[1]);

      expect(props.setEditingId).toHaveBeenCalledWith('q-2');
    });

    it('also starts editing on double click', async () => {
      const { props } = renderList();

      await userEvent.dblClick(screen.getByText('first task'));

      expect(props.setEditingId).toHaveBeenCalledWith('q-1');
    });

    it('saves multi-line text with Enter semantics: Enter saves, Shift+Enter keeps writing', async () => {
      const { props } = renderList({ editingId: 'q-1' });
      const editor = screen.getByRole('textbox', { name: 'Edit' });
      expect(editor).toHaveValue('first task');

      await userEvent.type(editor, '{Shift>}{Enter}{/Shift}second line');
      expect(props.editMessage).not.toHaveBeenCalled();

      await userEvent.type(editor, '{Enter}');

      expect(props.editMessage).toHaveBeenCalledWith('q-1', 'first task\nsecond line');
      expect(props.setEditingId).toHaveBeenCalledWith(null);
    });

    it('does not save on the Enter that confirms an IME candidate', () => {
      const { props } = renderList({ editingId: 'q-1' });
      const editor = screen.getByRole('textbox', { name: 'Edit' });

      fireEvent.keyDown(editor, { key: 'Enter', isComposing: true });

      expect(props.editMessage).not.toHaveBeenCalled();
    });

    it('does not let editor keys reach the composer form around the list', () => {
      const onFormKeyDown = vi.fn();
      render(
        // oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- mirrors the composer form that delegates key handling
        <form onKeyDown={onFormKeyDown}>
          <QueuedMessagesList
            queue={[message('q-1', 'first task')]}
            pausedReason={null}
            editingId="q-1"
            setEditingId={vi.fn()}
            editMessage={vi.fn()}
            removeMessage={vi.fn()}
            reorder={vi.fn()}
            resume={vi.fn()}
          />
        </form>,
      );

      fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit' }), { key: 'Enter' });
      fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit' }), { key: 'Escape' });

      expect(onFormKeyDown).not.toHaveBeenCalled();
    });

    it('cancels with Escape and with the cancel button without touching the message', async () => {
      const { props } = renderList({ editingId: 'q-1' });

      fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit' }), { key: 'Escape' });
      await userEvent.click(screen.getByRole('button', { name: 'Cancel edit' }));

      expect(props.setEditingId).toHaveBeenCalledTimes(2);
      expect(props.setEditingId).toHaveBeenNthCalledWith(1, null);
      expect(props.editMessage).not.toHaveBeenCalled();
    });

    it('refuses to save an empty message that has no attachments', async () => {
      const { props } = renderList({ editingId: 'q-1' });
      const editor = screen.getByRole('textbox', { name: 'Edit' });

      await userEvent.clear(editor);

      expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
      await userEvent.type(editor, '{Enter}');
      expect(props.editMessage).not.toHaveBeenCalled();
    });

    it('lets an attachment-only message be saved with empty text', async () => {
      const { props } = renderList({
        queue: [message('q-1', 'caption', { files: [{ id: 'f1' }] as never })],
        editingId: 'q-1',
      });

      await userEvent.clear(screen.getByRole('textbox', { name: 'Edit' }));
      await userEvent.click(screen.getByRole('button', { name: 'Save' }));

      expect(props.editMessage).toHaveBeenCalledWith('q-1', '');
    });

    it('releases the editor lock when the list goes away', () => {
      const { props, unmount } = renderList({ editingId: 'q-1' });
      expect(props.setEditingId).not.toHaveBeenCalled();

      unmount();

      expect(props.setEditingId).toHaveBeenCalledWith(null);
    });
  });
});
