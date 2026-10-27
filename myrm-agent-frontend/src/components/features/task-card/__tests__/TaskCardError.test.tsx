import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { TaskCardError } from '../TaskCardError';

describe('TaskCardError', () => {
  it('shows localized copy for a task interrupted by an app stop instead of the server message', () => {
    render(
      <TaskCardError
        error={{
          error_type: 'interrupted',
          message: 'The task was interrupted before it finished.',
          recoverable: 'transient',
        }}
      />,
    );

    expect(screen.getByText('interrupted')).toBeInTheDocument();
    expect(screen.queryByText('The task was interrupted before it finished.')).not.toBeInTheDocument();
  });

  it('shows the server message for other failures and offers retry only when transient', () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <TaskCardError
        error={{ error_type: 'ConnectionError', message: 'Provider unreachable', recoverable: 'transient' }}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText('Provider unreachable')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'retryTask' }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    rerender(
      <TaskCardError
        error={{ error_type: 'PermissionError', message: 'Key rejected', recoverable: 'permanent' }}
        onRetry={onRetry}
      />,
    );
    expect(screen.queryByRole('button', { name: 'retryTask' })).not.toBeInTheDocument();
  });
});
