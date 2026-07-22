import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { VideoTaskCard } from '../VideoTaskCard';

const mockUseTaskSubscription = vi.fn();

vi.mock('@/hooks/tasks/useTasksSubscription', () => ({
  useTaskSubscription: (...args: unknown[]) => mockUseTaskSubscription(...args),
}));

describe('VideoTaskCard', () => {
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
    render(<VideoTaskCard task_id="vid-1" />);
    expect(screen.getByText('Queued...')).toBeInTheDocument();
  });

  it('renders playable video on success', () => {
    mockUseTaskSubscription.mockReturnValue({
      task_id: 'vid-2',
      task_type: 'video_generate',
      status: 'succeeded',
      payload: { prompt: 'sunset' },
      result: {
        video_urls: ['https://cdn.example/video.mp4'],
        provider: 'openai',
        model: 'sora',
        latency_ms: 1450,
      },
      priority: 0,
      progress: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });

    const { container } = render(<VideoTaskCard task_id="vid-2" />);

    const videoElement = container.querySelector('video');
    expect(videoElement).not.toBeNull();
    expect(videoElement?.getAttribute('src')).toBe('https://cdn.example/video.mp4');
    expect(screen.getByText('providerLabel: openai')).toBeInTheDocument();
    expect(screen.getByText('modelLabel: sora')).toBeInTheDocument();
    expect(screen.getByText('latencyLabel: 1450ms')).toBeInTheDocument();
  });

  it('retries transient failure', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({}) }) as Response);
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    mockUseTaskSubscription.mockReturnValue({
      task_id: 'vid-3',
      task_type: 'video_generate',
      status: 'failed',
      payload: { prompt: 'sunset' },
      error: { error_type: 'timeout', message: 'timeout', recoverable: 'transient' },
      priority: 0,
      progress: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });

    render(<VideoTaskCard task_id="vid-3" />);
    fireEvent.click(screen.getByRole('button', { name: 'retryTask' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/tasks/vid-3/retry', { method: 'POST' });
    });
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
      task_id: 'vid-4',
      task_type: 'video_generate',
      status: 'failed',
      payload: { prompt: 'sunset' },
      error: { error_type: 'timeout', message: 'timeout', recoverable: 'transient' },
      priority: 0,
      progress: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });

    render(<VideoTaskCard task_id="vid-4" />);
    fireEvent.click(screen.getByRole('button', { name: 'retryTask' }));

    await waitFor(() => {
      expect(screen.getByText('Only failed tasks can be retried')).toBeInTheDocument();
    });
  });
});
