import contract from '@shared/config/media_generation_contract.json';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ImageTaskCard } from '../ImageTaskCard';
import { VideoTaskCard } from '../VideoTaskCard';

const mockUseTaskSubscription = vi.fn();

vi.mock('@/hooks/tasks/useTasksSubscription', () => ({
  useTaskSubscription: (...args: unknown[]) => mockUseTaskSubscription(...args),
}));

const { image_result: imageResult, video_result: videoResult } = contract.examples;

const mediaFileUrl = (reference: string) => new RegExp(`/api/v1/media/${reference.replace('media://', '')}/file$`);

function succeededTask(taskType: string, result: object) {
  return {
    task_id: 'contract-task',
    task_type: taskType,
    status: 'succeeded',
    payload: { prompt: 'a red fox in the snow' },
    result,
    priority: 0,
    progress: 100,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

// The results are the ones the server's contract test holds its executors to.
describe('the task cards against the shared results', () => {
  beforeEach(() => {
    mockUseTaskSubscription.mockReset();
  });

  it('ImageTaskCard shows the stored image with the model that made it', () => {
    mockUseTaskSubscription.mockReturnValue(succeededTask('image_generate', imageResult));

    render(<ImageTaskCard task_id="contract-task" />);

    expect(screen.getByRole('img').getAttribute('src')).toMatch(mediaFileUrl(imageResult.images[0].url));
    expect(screen.getByText(imageResult.model)).toBeInTheDocument();
  });

  it('VideoTaskCard plays the stored video', () => {
    mockUseTaskSubscription.mockReturnValue(succeededTask('video_generate', videoResult));

    const { container } = render(<VideoTaskCard task_id="contract-task" />);

    expect(container.querySelector('video')?.getAttribute('src')).toMatch(mediaFileUrl(videoResult.video_urls[0]));
  });
});
