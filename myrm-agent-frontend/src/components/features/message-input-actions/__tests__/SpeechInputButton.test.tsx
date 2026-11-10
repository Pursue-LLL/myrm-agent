import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/primitives/tooltip';
import type { SpeechState, useSpeechInput } from '@/hooks/voice/useSpeechInput';
import SpeechInputButton from '../SpeechInputButton';

type SpeechOptions = Parameters<typeof useSpeechInput>[0];

const kit = vi.hoisted(() => ({
  /** Keys are told apart from raw messages by their prefix. */
  t: (key: string) => `t:${key}`,
  toast: vi.fn<(options: { title: string; description: string }) => void>(),
  options: vi.fn<(options: SpeechOptions) => void>(),
  handlers: { toggle: vi.fn(), onPointerDown: vi.fn(), onPointerUp: vi.fn() },
  speech: {
    state: 'idle' as SpeechState,
    elapsed: 0,
    audioLevel: 0,
    interimText: '',
    isSupported: true,
  },
}));

vi.mock('next-intl', () => ({ useTranslations: () => kit.t }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: kit.toast }));
vi.mock('@/hooks/voice/useSpeechInput', () => ({
  useSpeechInput: (options: SpeechOptions) => {
    kit.options(options);
    return { ...kit.speech, ...kit.handlers };
  },
}));

beforeEach(() => {
  kit.speech.state = 'idle';
  kit.speech.elapsed = 0;
  kit.speech.audioLevel = 0;
  kit.speech.interimText = '';
  kit.speech.isSupported = true;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderSpeech(props: Partial<React.ComponentProps<typeof SpeechInputButton>> = {}) {
  return render(
    <TooltipProvider>
      <SpeechInputButton onTranscript={vi.fn()} {...props} />
    </TooltipProvider>,
  );
}

const button = () => screen.getByRole('button');
const waveformBars = (container: HTMLElement) => [...container.querySelectorAll<HTMLElement>('span.rounded-full')];

describe('SpeechInputButton availability', () => {
  it('renders nothing when speech input is not supported', () => {
    kit.speech.isSupported = false;
    const { container } = renderSpeech();

    expect(container).toBeEmptyDOMElement();
  });

  it('passes its settings to the speech input, with toggle mode and no sounds by default', () => {
    const onTranscript = vi.fn();
    const onInterimTranscript = vi.fn();
    renderSpeech({ onTranscript, onInterimTranscript });

    expect(kit.options).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        onTranscript,
        onInterimTranscript,
        mode: 'toggle',
        enableSounds: false,
        keyterms: undefined,
      }),
    );
  });

  it('passes explicit mode, sounds and key terms on', () => {
    renderSpeech({ mode: 'push-to-talk', enableSounds: true, keyterms: ['Myrm'] });

    expect(kit.options).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ mode: 'push-to-talk', enableSounds: true, keyterms: ['Myrm'] }),
    );
  });
});

describe('SpeechInputButton in toggle mode', () => {
  it('offers to start recording, and a click toggles', () => {
    renderSpeech();

    expect(button()).toHaveAccessibleName('t:startRecording');
    fireEvent.click(button());

    expect(kit.handlers.toggle).toHaveBeenCalledTimes(1);
  });

  it('ignores the pointer events that push-to-talk uses', () => {
    renderSpeech();

    fireEvent.pointerDown(button());
    fireEvent.pointerUp(button());

    expect(kit.handlers.onPointerDown).not.toHaveBeenCalled();
    expect(kit.handlers.onPointerUp).not.toHaveBeenCalled();
  });

  it('does not treat the pointer leaving as a release while recording', () => {
    kit.speech.state = 'recording';
    renderSpeech();

    fireEvent.pointerLeave(button());

    expect(kit.handlers.onPointerUp).not.toHaveBeenCalled();
  });

  it('offers to stop while recording, with the elapsed time and a waveform', () => {
    kit.speech.state = 'recording';
    kit.speech.elapsed = 65;
    const { container } = renderSpeech();

    expect(button()).toHaveAccessibleName('t:stopRecording');
    expect(screen.getByText('1:05')).toBeInTheDocument();
    expect(waveformBars(container)).toHaveLength(5);
    fireEvent.click(button());
    expect(kit.handlers.toggle).toHaveBeenCalledTimes(1);
  });

  it.each([
    [0, '0:00'],
    [5, '0:05'],
    [59, '0:59'],
    [60, '1:00'],
    [3599, '59:59'],
  ])('writes %i seconds as %s', (elapsed, text) => {
    kit.speech.state = 'recording';
    kit.speech.elapsed = elapsed;
    renderSpeech();

    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('shows no timer or waveform while idle', () => {
    const { container } = renderSpeech();

    expect(screen.queryByText('0:00')).toBeNull();
    expect(waveformBars(container)).toHaveLength(0);
  });
});

describe('SpeechInputButton while transcribing', () => {
  it('is disabled, says it is transcribing and spins', () => {
    kit.speech.state = 'transcribing';
    const { container } = renderSpeech();

    expect(button()).toBeDisabled();
    expect(button()).toHaveAccessibleName('t:transcribing');
    expect(button()).toHaveClass('opacity-50', 'cursor-not-allowed');
    expect(container.querySelector('.animate-spin')).not.toBeNull();
    fireEvent.click(button());
    expect(kit.handlers.toggle).not.toHaveBeenCalled();
  });
});

describe('SpeechInputButton appearance', () => {
  it('is a round microphone button while idle', () => {
    const { container } = renderSpeech();

    expect(button()).toHaveClass('w-8');
    expect(button()).not.toHaveClass('text-red-600');
    expect(container.querySelector('.lucide-mic')).not.toBeNull();
    expect(container.querySelector('.lucide-mic-off')).toBeNull();
  });

  it('turns into a red pill with a crossed-out microphone while recording', () => {
    kit.speech.state = 'recording';
    const { container } = renderSpeech();

    expect(button()).toHaveClass('px-2.5', 'text-red-600');
    expect(button()).not.toHaveClass('w-8');
    expect(container.querySelector('.lucide-mic-off')).not.toBeNull();
    expect(container.querySelector('.lucide-mic')).toBeNull();
  });
});

describe('SpeechInputButton when disabled', () => {
  it('cannot be used and looks it', () => {
    renderSpeech({ disabled: true });

    expect(button()).toBeDisabled();
    expect(button()).toHaveClass('opacity-50', 'cursor-not-allowed');
  });

  it('looks and behaves normally when enabled', () => {
    renderSpeech();

    expect(button()).toBeEnabled();
    expect(button()).not.toHaveClass('opacity-50');
  });
});

describe('SpeechInputButton in push-to-talk mode', () => {
  it('offers to hold, starts on press and stops on release, and a click does nothing', () => {
    renderSpeech({ mode: 'push-to-talk' });

    expect(button()).toHaveAccessibleName('t:holdToTalk');
    fireEvent.pointerDown(button());
    expect(kit.handlers.onPointerDown).toHaveBeenCalledTimes(1);
    fireEvent.pointerUp(button());
    expect(kit.handlers.onPointerUp).toHaveBeenCalledTimes(1);
    fireEvent.click(button());
    expect(kit.handlers.toggle).not.toHaveBeenCalled();
  });

  it('does not stop when the pointer leaves while nothing is being recorded', () => {
    renderSpeech({ mode: 'push-to-talk' });

    fireEvent.pointerLeave(button());

    expect(kit.handlers.onPointerUp).not.toHaveBeenCalled();
  });

  it('says to release while recording, and stops when the pointer leaves the button', () => {
    kit.speech.state = 'recording';
    renderSpeech({ mode: 'push-to-talk' });

    expect(button()).toHaveAccessibleName('t:releaseToStop');
    fireEvent.pointerLeave(button());

    expect(kit.handlers.onPointerUp).toHaveBeenCalledTimes(1);
  });
});

describe('SpeechInputButton interim text', () => {
  it('shows what has been heard so far while recording', () => {
    kit.speech.state = 'recording';
    kit.speech.interimText = 'hello wor';
    renderSpeech();

    expect(screen.getByText('hello wor')).toBeInTheDocument();
  });

  it('shows nothing extra when nothing has been heard yet', () => {
    kit.speech.state = 'recording';
    const { container } = renderSpeech();

    expect(container.querySelector('.animate-pulse')).toBeNull();
  });

  it('hides leftover text when not recording', () => {
    kit.speech.interimText = 'stale';
    renderSpeech();

    expect(screen.queryByText('stale')).toBeNull();
  });
});

describe('SpeechInputButton waveform', () => {
  const heights = (container: HTMLElement) => waveformBars(container).map((bar) => bar.style.height);

  it('rests at a low level when it is silent', () => {
    kit.speech.state = 'recording';
    kit.speech.audioLevel = 0;
    const { container } = renderSpeech();

    expect(heights(container)).toEqual(['20%', '20%', '20%', '20%', '20%']);
  });

  it('peaks in the middle and falls off towards the edges at full volume', () => {
    kit.speech.state = 'recording';
    kit.speech.audioLevel = 1;
    const { container } = renderSpeech();

    expect(heights(container)).toEqual(['50%', '75%', '100%', '75%', '50%']);
  });

  it('never grows past the full height', () => {
    kit.speech.state = 'recording';
    kit.speech.audioLevel = 5;
    const { container } = renderSpeech();

    expect(heights(container)).toEqual(['100%', '100%', '100%', '100%', '100%']);
  });
});

describe('SpeechInputButton reporting problems', () => {
  const reportError = (message: string) => {
    renderSpeech();
    kit.options.mock.calls[0][0].onError?.(message);
  };

  it('explains a recording that was too short in the user language', () => {
    reportError('tooShort');

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 't:error', description: 't:tooShort' });
  });

  it('passes any other message through as it is', () => {
    reportError('Microphone permission denied');

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 't:error',
      description: 'Microphone permission denied',
    });
  });
});
