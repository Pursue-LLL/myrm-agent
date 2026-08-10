import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act, fireEvent } from '@testing-library/react';
import type { VoiceSessionState } from '@/hooks/voice/useVoiceSession';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const voiceMock = vi.hoisted(() => ({
  speakResponse: vi.fn(),
  startSession: vi.fn(),
  stopSession: vi.fn(),
  interruptTTS: vi.fn(),
}));

const chatStoreMock = vi.hoisted(() => ({
  chatId: 'chat-1',
  messages: [] as Array<{ messageId?: string; role: string; content: string }>,
  loading: false,
  sendMessage: vi.fn(),
  setCameraFrames: vi.fn(),
  agentConfig: undefined as { agentId?: string } | undefined,
}));

const voiceSessionMock = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/voice/useVoiceSession', () => ({
  useVoiceSession: (...args: unknown[]) => voiceSessionMock(...args),
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof chatStoreMock) => unknown) => selector(chatStoreMock),
}));

vi.mock('@/components/features/voice/VoiceSessionOverlay', () => ({
  default: () => null,
}));

vi.mock('@/components/features/settings/Tooltip', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import VoiceSessionButton from '../VoiceSessionButton';

interface VoiceSessionShape {
  sessionState: VoiceSessionState;
  isActive: boolean;
}

function mockVoiceSession(shape: VoiceSessionShape) {
  voiceSessionMock.mockReturnValue({
    sessionState: shape.sessionState,
    isActive: shape.isActive,
    startSession: voiceMock.startSession,
    stopSession: voiceMock.stopSession,
    interruptTTS: voiceMock.interruptTTS,
    speakResponse: voiceMock.speakResponse,
    interimText: '',
    audioLevel: 0,
    cameraState: 'inactive',
    facingMode: 'user',
    videoRef: { current: null },
    toggleFacing: vi.fn(),
    ttsState: 'idle',
    agentResponseText: '',
    agentToolName: '',
  });
}

function emitVoiceBgDone(chatId: string, title?: string, message?: string) {
  window.dispatchEvent(
    new CustomEvent('voice-bg-done', {
      detail: { title, message, chat_id: chatId },
    }),
  );
}

describe('VoiceSessionButton voice background task announcement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatStoreMock.chatId = 'chat-1';
    chatStoreMock.messages = [];
    chatStoreMock.loading = false;

    localStorage.setItem('voiceSessionEnabled', 'true');
    localStorage.setItem('voiceFullDuplexEnabled', 'true');
    localStorage.setItem('voiceSessionMode', 'audio_only');
  });

  it('announces a background task completion via speakResponse with queue flag', () => {
    mockVoiceSession({ sessionState: 'listening', isActive: true });
    render(<VoiceSessionButton />);

    act(() => {
      emitVoiceBgDone('chat-1', 'Task completed', 'Your report is ready.');
    });

    expect(voiceMock.speakResponse).toHaveBeenCalledWith('Task completed', { queue: true });
  });

  it('falls back to message text when title is missing', () => {
    mockVoiceSession({ sessionState: 'listening', isActive: true });
    render(<VoiceSessionButton />);

    act(() => {
      emitVoiceBgDone('chat-1', undefined, 'Report generated.');
    });

    expect(voiceMock.speakResponse).toHaveBeenCalledWith('Report generated.', { queue: true });
  });

  it('does not announce when chat_id does not match the active chat', () => {
    mockVoiceSession({ sessionState: 'listening', isActive: true });
    render(<VoiceSessionButton />);

    act(() => {
      emitVoiceBgDone('chat-999', 'Wrong chat', 'Should be ignored.');
    });

    expect(voiceMock.speakResponse).not.toHaveBeenCalled();
  });

  it('does not announce when no title and no message', () => {
    mockVoiceSession({ sessionState: 'listening', isActive: true });
    render(<VoiceSessionButton />);

    act(() => {
      emitVoiceBgDone('chat-1', undefined, undefined);
    });

    expect(voiceMock.speakResponse).not.toHaveBeenCalled();
  });

  it('defers the announcement while the agent is speaking, then flushes after it stops', () => {
    mockVoiceSession({ sessionState: 'speaking', isActive: true });
    // Pass a changing prop so the memo component re-renders on the state flip.
    const { rerender } = render(<VoiceSessionButton keyterms={['a']} />);

    act(() => {
      emitVoiceBgDone('chat-1', 'Deferred title');
    });
    // Agent is mid-utterance: not announced yet.
    expect(voiceMock.speakResponse).not.toHaveBeenCalled();

    // Agent stops speaking → flush deferred announcement.
    mockVoiceSession({ sessionState: 'listening', isActive: true });
    rerender(<VoiceSessionButton keyterms={['b']} />);

    expect(voiceMock.speakResponse).toHaveBeenCalledWith('Deferred title', { queue: true });
  });

  it('does not register listener when voice session is inactive', () => {
    mockVoiceSession({ sessionState: 'inactive', isActive: false });
    render(<VoiceSessionButton />);

    act(() => {
      emitVoiceBgDone('chat-1', 'Ignored title');
    });

    expect(voiceMock.speakResponse).not.toHaveBeenCalled();
  });

  it('deferred announcements do not leak across chats after chat switch', () => {
    mockVoiceSession({ sessionState: 'speaking', isActive: true });
    const { rerender } = render(<VoiceSessionButton keyterms={['a']} />);

    act(() => {
      emitVoiceBgDone('chat-1', 'Queued for chat-1');
    });
    expect(voiceMock.speakResponse).not.toHaveBeenCalled();

    // Switch to another chat: flush should still announce the queued text (chat-scoped listener).
    chatStoreMock.chatId = 'chat-2';
    mockVoiceSession({ sessionState: 'listening', isActive: true });
    rerender(<VoiceSessionButton keyterms={['b']} />);

    expect(voiceMock.speakResponse).toHaveBeenCalledWith('Queued for chat-1', { queue: true });
  });

  it('toggles session on button click', () => {
    mockVoiceSession({ sessionState: 'listening', isActive: true });
    const { getByRole } = render(<VoiceSessionButton />);

    fireEvent.click(getByRole('button'));
    expect(voiceMock.stopSession).toHaveBeenCalledOnce();
  });
});
