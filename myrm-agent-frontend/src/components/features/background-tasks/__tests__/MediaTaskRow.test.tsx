import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { Task } from '@/store/tasks/types';
import { MediaTaskRow } from '../MediaTaskRow';

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace?: string) => (key: string) => (namespace ? `${namespace}.${key}` : key),
}));

function failedTask(error: Task['error']): Task {
  return {
    task_id: 'task-1',
    task_type: 'image_generate',
    status: 'failed',
    progress: 0,
    payload: {},
    error,
    created_at: '2026-10-27T00:00:00Z',
    updated_at: '2026-10-27T00:00:00Z',
  } as Task;
}

describe('MediaTaskRow', () => {
  it('shows localized copy for a task interrupted by an app stop instead of the server message', () => {
    render(
      <MediaTaskRow
        task={failedTask({
          error_type: 'interrupted',
          message: 'The task was interrupted before it finished because the app stopped.',
          recoverable: 'transient',
        })}
        variant="terminal"
        onNavigateChat={vi.fn()}
      />,
    );

    expect(screen.getByText('taskCard.interrupted')).toBeInTheDocument();
    expect(screen.queryByText(/interrupted before it finished/)).not.toBeInTheDocument();
  });

  it('shows the server message for other failures', () => {
    render(
      <MediaTaskRow
        task={failedTask({ error_type: 'ConnectionError', message: 'Provider unreachable', recoverable: 'transient' })}
        variant="terminal"
        onNavigateChat={vi.fn()}
      />,
    );

    expect(screen.getByText('Provider unreachable')).toBeInTheDocument();
  });
});
