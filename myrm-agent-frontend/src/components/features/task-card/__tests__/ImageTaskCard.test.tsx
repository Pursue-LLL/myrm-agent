import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ImageTaskCard } from '../ImageTaskCard';

const mockUseTaskSubscription = vi.fn();

vi.mock('@/hooks/tasks/useTasksSubscription', () => ({
  useTaskSubscription: (...args: unknown[]) => mockUseTaskSubscription(...args),
}));

describe('ImageTaskCard', () => {
  beforeEach(() => {
    mockUseTaskSubscription.mockReset();
    Object.defineProperty(global, 'fetch', {
      value: vi.fn(async () => ({ ok: true, json: async () => ({}) }) as Response),
      writable: true,
      configurable: true,
    });
  });

  it('renders placeholder while task is loading', () => {
    mockUseTaskSubscription.mockReturnValue(undefined);
    render(<ImageTaskCard task_id="img-1" />);
    expect(screen.getByText('Queued...')).toBeInTheDocument();
  });

  it('shows structured retry error message when retry request fails', async () => {
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: false,
          status: 400,
          json: async () => ({
            detail: {
              code: 'TASK_NOT_RETRYABLE',
              message: 'Only failed tasks can be retried',
              recoverable: 'permanent',
            },
          }),
        }) as Response,
    );
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    mockUseTaskSubscription.mockReturnValue({
      task_id: 'img-2',
      task_type: 'image_generate',
      status: 'failed',
      payload: { prompt: 'forest' },
      error: { error_type: 'timeout', message: 'timeout', recoverable: 'transient' },
      priority: 0,
      progress: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });

    render(<ImageTaskCard task_id="img-2" />);
    fireEvent.click(screen.getByRole('button', { name: 'retryTask' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/tasks/img-2/retry', { method: 'POST' });
      expect(screen.getByText('Only failed tasks can be retried')).toBeInTheDocument();
    });
  });
});

