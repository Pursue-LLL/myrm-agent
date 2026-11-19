import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import TtsAudioCard from '../TtsAudioCard';

describe('TtsAudioCard', () => {
  it('plays a media-library reference through the media endpoint', () => {
    const { container } = render(<TtsAudioCard url="media://media_speech" />);

    expect(container.querySelector('audio')?.getAttribute('src')).toMatch(/\/api\/v1\/media\/media_speech\/file$/);
  });

  it('shows the model and the duration when it has them', () => {
    const { getByText } = render(
      <TtsAudioCard url="media://media_speech" model="gpt-4o-mini-tts" durationSeconds={2.5} />,
    );

    expect(getByText('gpt-4o-mini-tts · 2.5s')).toBeInTheDocument();
  });

  it('replaces the player with the playback error when the file cannot be played', () => {
    const { container, getByText } = render(<TtsAudioCard url="media://media_gone" />);

    fireEvent.error(container.querySelector('audio') as HTMLAudioElement);

    expect(getByText('playbackFailed')).toBeInTheDocument();
    expect(container.querySelector('audio')).toBeNull();
  });
});
