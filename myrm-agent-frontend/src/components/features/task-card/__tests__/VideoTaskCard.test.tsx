import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

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
    expect(screen.getByText('Provider / 提供商: openai')).toBeInTheDocument();
    expect(screen.getByText('Model / 模型: sora')).toBeInTheDocument();
    expect(screen.getByText('Latency / 延迟: 1450ms')).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', { name: 'Retry Task' }));

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/tasks/vid-3/retry', { method: 'POST' });
  });
});
