import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { MediaGeneratedEntry } from '@/lib/chat/mediaGenerated';
import { GeneratedMediaCards } from '../GeneratedMediaCards';

type Props = Record<string, unknown>;

const editImage = vi.fn();

vi.mock('@/components/features/task-card', () => ({
  ImageTaskCard: (props: Props) => <div data-testid="image-task" data-task={String(props.task_id)} />,
  VideoTaskCard: (props: Props) => <div data-testid="video-task" data-task={String(props.task_id)} />,
}));
vi.mock('@/components/features/message-box/TtsAudioCard', () => ({
  default: (props: Props) => (
    <div
      data-testid="tts"
      data-url={String(props.url)}
      data-model={String(props.model)}
      data-duration={String(props.durationSeconds)}
    />
  ),
}));
vi.mock('@/components/features/image-gen/useEditGeneratedImage', () => ({
  useEditGeneratedImage: () => editImage,
}));
vi.mock('@/components/features/image-gen/ImageResultCard', () => ({
  ImageResultCard: (props: {
    images: { url: string }[];
    model?: string;
    onEditRequest?: (image: { url: string }) => void;
  }) => (
    <button
      type="button"
      aria-label="edit image"
      data-testid="image-result"
      data-url={props.images[0].url}
      data-model={String(props.model)}
      onClick={() => props.onEditRequest?.(props.images[0])}
    />
  ),
}));

function renderCards(entries: MediaGeneratedEntry[]) {
  return render(
    <div data-testid="host">
      <GeneratedMediaCards entries={entries} />
    </div>,
  );
}

describe('GeneratedMediaCards', () => {
  it('shows an image task card and a video task card for the async entries', () => {
    renderCards([
      { kind: 'image', task_id: 'img-1' },
      { kind: 'video', task_id: 'vid-1' },
    ]);

    expect(screen.getByTestId('image-task').getAttribute('data-task')).toBe('img-1');
    expect(screen.getByTestId('video-task').getAttribute('data-task')).toBe('vid-1');
  });

  it('shows one card per task when a call generated several images', () => {
    renderCards([
      { kind: 'image', task_id: 'img-1' },
      { kind: 'image', task_id: 'img-2' },
      { kind: 'image', task_id: 'img-3' },
    ]);

    expect(screen.getAllByTestId('image-task').map((card) => card.getAttribute('data-task'))).toEqual([
      'img-1',
      'img-2',
      'img-3',
    ]);
  });

  it('plays stored speech in place with its model and duration', () => {
    renderCards([{ kind: 'tts', media: 'media://media_speech', model: 'gpt-4o-mini-tts', duration_seconds: 2.5 }]);

    const player = screen.getByTestId('tts');
    expect(player.getAttribute('data-url')).toBe('media://media_speech');
    expect(player.getAttribute('data-model')).toBe('gpt-4o-mini-tts');
    expect(player.getAttribute('data-duration')).toBe('2.5');
  });

  it('shows a stored image right away and hands exactly that image to the edit action', () => {
    renderCards([{ kind: 'image', media: 'media://media_edit', model: 'gpt-image-2.6-sunburst' }]);

    const card = screen.getByTestId('image-result');
    expect(card.getAttribute('data-url')).toBe('media://media_edit');
    expect(card.getAttribute('data-model')).toBe('gpt-image-2.6-sunburst');

    card.click();
    expect(editImage).toHaveBeenCalledWith({ url: 'media://media_edit' });
  });

  it('keeps the order in which the tools produced the media, as siblings without a wrapper', () => {
    renderCards([
      { kind: 'tts', media: 'media://media_speech' },
      { kind: 'video', task_id: 'vid-1' },
      { kind: 'image', task_id: 'img-1' },
    ]);

    const host = screen.getByTestId('host');
    expect(Array.from(host.children).map((child) => child.getAttribute('data-testid'))).toEqual([
      'tts',
      'video-task',
      'image-task',
    ]);
  });

  it('renders nothing for no entries', () => {
    renderCards([]);

    expect(screen.getByTestId('host').children).toHaveLength(0);
  });
});
