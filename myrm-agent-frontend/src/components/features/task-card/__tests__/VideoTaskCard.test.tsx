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
    expect(screen.getByText('queued')).toBeInTheDocument();
  });

  it('renders playable video on success', () => {
    mockUseTaskSubscription.mockReturnValue({
      task_id: 'vid-2',
      task_type: 'video_generate',
      status: 'succeeded',
      payload: { prompt: 'sunset' },
      result: {
        video_urls: ['https://cdn.example/video.mp4'],
        provider: 'gemini',
        model: 'veo-3.1-fast-generate-preview',
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
    expect(screen.getByText('providerLabel: gemini')).toBeInTheDocument();
    expect(screen.getByText('modelLabel: veo-3.1-fast-generate-preview')).toBeInTheDocument();
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

  describe('a finished task', () => {
    const finished = (result: Record<string, unknown> | undefined) => ({
      task_id: 'vid-ok',
      task_type: 'video_generate',
      status: 'succeeded',
      payload: { prompt: 'sunset' },
      result,
      priority: 0,
      progress: 100,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });

    it('plays the stored video the executor result names', () => {
      mockUseTaskSubscription.mockReturnValue(
        finished({ video_urls: ['media://media_vid'], model: 'seedance-2-0', prompt: 'sunset', latency_ms: 90000 }),
      );

      const { container } = render(<VideoTaskCard task_id="vid-ok" />);

      expect(container.querySelector('video')?.getAttribute('src')).toMatch(/\/api\/v1\/media\/media_vid\/file$/);
      expect(screen.getByText('modelLabel: seedance-2-0')).toBeInTheDocument();
      expect(screen.queryByText(/providerLabel/)).toBeNull();
    });

    it.each([
      ['has no result', undefined],
      ['names no video', { model: 'seedance-2-0', video_urls: [] }],
      ['names videos without an address', { video_urls: ['', 5] }],
    ])('says the result cannot be shown, rather than rendering nothing, when it %s', (_label, result) => {
      mockUseTaskSubscription.mockReturnValue(finished(result));

      const { container } = render(<VideoTaskCard task_id="vid-ok" />);

      expect(screen.getByText('resultUnavailable')).toBeInTheDocument();
      expect(container.querySelector('video')).toBeNull();
    });
  });

  it('says the task record has expired and points to the media library when the server no longer has it', () => {
    mockUseTaskSubscription.mockReturnValue(null);

    render(<VideoTaskCard task_id="vid-pruned" />);

    expect(screen.getByText(/expired/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'openLibrary' }).getAttribute('href')).toBe('/library');
  });
});
