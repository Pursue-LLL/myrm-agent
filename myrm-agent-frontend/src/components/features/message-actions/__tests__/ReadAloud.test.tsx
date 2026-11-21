import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TTSState } from '@/hooks/voice/tts/types';
import { useSpeakingRowStore } from '@/store/useSpeakingRowStore';
import ReadAloud from '../ReadAloud';

// A stand-in engine with the real contract: stopping returns it to idle, and the test moves it between the other states.
const engine = vi.hoisted(() => ({
  setState: (_state: TTSState) => {},
  stop: vi.fn(),
}));

vi.mock('@/hooks/voice/useTTS', async () => {
  const { useCallback, useState } = await import('react');
  return {
    useTTS: () => {
      const [state, setState] = useState<TTSState>('idle');
      engine.setState = setState;
      const stop = useCallback(() => {
        engine.stop();
        setState('idle');
      }, []);
      return { state, supported: true, toggle: vi.fn(), stop, speak: vi.fn(), pause: vi.fn(), resume: vi.fn() };
    },
  };
});
vi.mock('@/store/useConfigStore', () => ({
  default: (select: (state: { webTtsProvider: string }) => unknown) => select({ webTtsProvider: 'browser' }),
}));
vi.mock('@/store/useFeatureGateStore', () => ({
  useFeatureGateStore: (select: (state: { isEnabled: () => boolean }) => unknown) => select({ isEnabled: () => true }),
}));

const ROW = 7;
const speakingRow = () => useSpeakingRowStore.getState().rowIndex;
const speak = (state: TTSState) => act(() => engine.setState(state));
const renderRow = (content = 'first answer', messageIndex = ROW) =>
  render(<ReadAloud content={content} messageIndex={messageIndex} />);

beforeEach(() => {
  vi.clearAllMocks();
  useSpeakingRowStore.setState({ rowIndex: null });
});

describe('ReadAloud speaking row', () => {
  it('claims no row while idle', () => {
    renderRow();

    expect(speakingRow()).toBeNull();
  });

  it('claims its row from the moment speech is requested until it ends', () => {
    renderRow();

    speak('loading');
    expect(speakingRow()).toBe(ROW);
    speak('playing');
    expect(speakingRow()).toBe(ROW);
    speak('paused');
    expect(speakingRow()).toBe(ROW);
    speak('idle');
    expect(speakingRow()).toBeNull();
  });

  it('ends the speech and gives up the row when it starts showing other text', () => {
    const { rerender } = renderRow('first answer');
    speak('playing');

    rerender(<ReadAloud content="an older message" messageIndex={ROW} />);

    expect(engine.stop).toHaveBeenCalled();
    expect(speakingRow()).toBeNull();
    expect(screen.queryByLabelText('tts.stop')).not.toBeInTheDocument();
  });

  it('leaves the speech alone while the text stays the same', () => {
    const { rerender } = renderRow('first answer');
    speak('playing');

    rerender(<ReadAloud content="first answer" messageIndex={ROW} />);

    expect(engine.stop).not.toHaveBeenCalled();
    expect(speakingRow()).toBe(ROW);
  });

  it('gives up the row when it unmounts mid-speech', () => {
    const { unmount } = renderRow();
    speak('playing');

    unmount();

    expect(speakingRow()).toBeNull();
  });

  it('does not clear the claim of the row that took the speech over', () => {
    renderRow();
    speak('playing');

    act(() => useSpeakingRowStore.getState().claim(9));
    speak('idle');

    expect(speakingRow()).toBe(9);
  });
});
