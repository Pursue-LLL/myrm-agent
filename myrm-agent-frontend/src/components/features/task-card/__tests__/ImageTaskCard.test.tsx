import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ImageTaskCard } from '../ImageTaskCard';

const mockUseTaskSubscription = vi.fn();

vi.mock('@/hooks/tasks/useTasksSubscription', () => ({
  useTaskSubscription: (...args: unknown[]) => mockUseTaskSubscription(...args),
}));

const TASK_DEFAULTS = {
  priority: 0,
  progress: 100,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function succeededImageTask(result: Record<string, unknown> | undefined, payload: Record<string, unknown> = {}) {
  return {
    ...TASK_DEFAULTS,
    task_id: 'img-ok',
    task_type: 'image_generate',
    status: 'succeeded',
    payload: { prompt: 'a red fox', size: '1024x1024', ...payload },
    result,
  };
}

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
    expect(screen.getByText('queued')).toBeInTheDocument();
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

  describe('a finished task', () => {
    // The executor result of a real generation: no `provider`, the image is a media-library reference.
    const executorResult = {
      images: [{ url: 'media://media_abc', mime_type: 'image/png' }],
      model: 'gpt-image-2.6-sunburst',
      prompt: 'a red fox',
      latency_ms: 4200,
    };

    it('shows the stored image with its prompt and model although the result names no provider', () => {
      mockUseTaskSubscription.mockReturnValue(succeededImageTask(executorResult));

      render(<ImageTaskCard task_id="img-ok" />);

      expect(screen.getByRole('img').getAttribute('src')).toMatch(/\/api\/v1\/media\/media_abc\/file$/);
      expect(screen.getByText('a red fox')).toBeInTheDocument();
      expect(screen.getByText('gpt-image-2.6-sunburst')).toBeInTheDocument();
      expect(screen.getByText('1024x1024')).toBeInTheDocument();
    });

    it('offers the edit action for an image that lives in the media library', () => {
      mockUseTaskSubscription.mockReturnValue(succeededImageTask(executorResult));

      render(<ImageTaskCard task_id="img-ok" />);

      expect(screen.getByRole('button', { name: 'editThisImage' })).toBeInTheDocument();
    });

    it('offers no edit action for an image that is only a plain URL, because nothing could reference it', () => {
      mockUseTaskSubscription.mockReturnValue(
        succeededImageTask({ ...executorResult, images: [{ url: 'https://cdn.example/fox.png' }] }),
      );

      render(<ImageTaskCard task_id="img-ok" />);

      expect(screen.getByRole('img').getAttribute('src')).toBe('https://cdn.example/fox.png');
      expect(screen.queryByRole('button', { name: 'editThisImage' })).toBeNull();
    });

    it.each([
      ['has no result', undefined],
      ['has no images', { model: 'gpt-image-2.6-sunburst', images: [] }],
      ['has no model', { images: [{ url: 'media://media_abc' }] }],
      ['has images without an address', { model: 'm', images: [{ url: '' }, 'oops', null] }],
    ])('says the result cannot be shown, rather than rendering nothing, when it %s', (_label, result) => {
      mockUseTaskSubscription.mockReturnValue(succeededImageTask(result));

      const { container } = render(<ImageTaskCard task_id="img-ok" />);

      expect(screen.getByText('resultUnavailable')).toBeInTheDocument();
      expect(container.querySelector('img')).toBeNull();
    });
  });

  it('says the task record has expired and points to the media library when the server no longer has it', () => {
    mockUseTaskSubscription.mockReturnValue(null);

    render(<ImageTaskCard task_id="img-pruned" />);

    expect(screen.getByText(/expired/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'openLibrary' }).getAttribute('href')).toBe('/library');
    expect(screen.queryByText('queued')).toBeNull();
  });

  it('says a cancelled task was cancelled', () => {
    mockUseTaskSubscription.mockReturnValue({
      ...TASK_DEFAULTS,
      task_id: 'img-cancelled',
      task_type: 'image_generate',
      status: 'cancelled',
      payload: {},
    });

    render(<ImageTaskCard task_id="img-cancelled" />);

    expect(screen.getByText('cancelled')).toBeInTheDocument();
  });
});
