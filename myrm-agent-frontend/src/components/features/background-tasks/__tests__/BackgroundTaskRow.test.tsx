/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MockLocale } from '@/test-utils/realIntl';

const intl = vi.hoisted(() => ({ locale: 'en' as MockLocale }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import type { BackgroundTask } from '@/services/background-tasks';
import { BackgroundTaskRow } from '../BackgroundTaskRow';

function failedShellTask(errorCategory: string): BackgroundTask {
  return {
    kind: 'shell',
    task_id: 'task-1',
    prompt: 'bun run build',
    status: 'failed',
    created_at: 1_790_000_000,
    completed_at: 1_790_000_060,
    result_preview: null,
    exit_code: 137,
    error_category: errorCategory,
  };
}

function renderRow(task: BackgroundTask) {
  render(
    <BackgroundTaskRow
      task={task}
      allowSteer={false}
      allowShellInput={false}
      steerTaskId={null}
      shellInputTaskId={null}
      steerInput=""
      shellInput=""
      onSteerInputChange={vi.fn()}
      onShellInputChange={vi.fn()}
      onToggleSteer={vi.fn()}
      onToggleShellInput={vi.fn()}
      onSteer={vi.fn()}
      onShellInputSend={vi.fn()}
      onShellInputClose={vi.fn()}
      onPromptOptionSelect={vi.fn()}
      onCancel={vi.fn()}
      onStopLeftover={vi.fn()}
      onNavigateChat={vi.fn()}
    />,
  );
}

describe('BackgroundTaskRow error category', () => {
  afterEach(() => {
    cleanup();
    intl.locale = 'en';
  });

  it('shows the translated reason a failed shell task ended with', () => {
    renderRow(failedShellTask('oom_killed'));

    expect(screen.getByText('OOM Killed')).toBeInTheDocument();
    expect(screen.queryByText(/errorCategories/)).toBeNull();
  });

  it('follows the interface language', () => {
    intl.locale = 'zh';
    renderRow(failedShellTask('segfault'));

    expect(screen.getByText('段错误 (Segfault)')).toBeInTheDocument();
  });

  it('shows a category the language pack does not know as the server sent it', () => {
    renderRow(failedShellTask('brand_new_category'));

    expect(screen.getByText('brand_new_category')).toBeInTheDocument();
    expect(screen.queryByText(/errorCategories/)).toBeNull();
  });
});
