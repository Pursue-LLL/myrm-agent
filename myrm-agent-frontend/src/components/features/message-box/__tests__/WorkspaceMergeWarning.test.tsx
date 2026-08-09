import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { WorkspaceMergeWarning } from '../WorkspaceMergeWarning';

const stableT = (key: string, params?: { count?: number }) => {
  if (key === 'message.workspaceMergeFailedTitle') return 'Workspace Merge Failed';
  if (key === 'message.workspaceMergeFailed') return `${params?.count ?? 0} merge errors`;
  if (key === 'message.workspaceMergeFailedMore') return `${params?.count ?? 0} more hidden`;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('WorkspaceMergeWarning', () => {
  it('renders collapsed panel with data-testid and expands to show error text', () => {
    render(
      <WorkspaceMergeWarning
        failures={[{ message: 'task_index=1: No space left on device' }]}
        failedCount={1}
      />,
    );

    expect(screen.getByTestId('workspace-merge-warning')).toBeTruthy();
    expect(screen.getByText('Workspace Merge Failed')).toBeTruthy();
    expect(screen.queryByText('task_index=1: No space left on device')).toBeNull();

    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('task_index=1: No space left on device')).toBeTruthy();
  });

  it('shows truncated-more hint when truncated count is provided', () => {
    render(
      <WorkspaceMergeWarning
        failures={[{ message: 'task_index=1: boom' }]}
        failedCount={3}
        truncated={2}
      />,
    );

    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('2 more hidden')).toBeTruthy();
  });
});
