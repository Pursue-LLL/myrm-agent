/**
 * A voice background task that finishes is announced over the session: by its title or message, queued behind
 * whatever the agent is saying, and only for the chat the session belongs to.
 */
import { act, fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { LISTENING, enableVoice, kit, mockVoiceSession, renderVoiceButton, resetVoiceKit } from './voiceSessionKit';

function emitVoiceBgDone(chatId: string, title?: string, message?: string) {
  window.dispatchEvent(
    new CustomEvent('voice-bg-done', {
      detail: { title, message, chat_id: chatId },
    }),
  );
}

describe('VoiceSessionButton voice background task announcement', () => {
  beforeEach(() => {
    resetVoiceKit();
    enableVoice({ fullDuplex: 'true', mode: 'audio_only' });
  });

  it('announces a background task completion via speakResponse with queue flag', () => {
    mockVoiceSession(LISTENING);
    renderVoiceButton();

    act(() => {
      emitVoiceBgDone('chat-1', 'Task completed', 'Your report is ready.');
    });

    expect(kit.voice.speakResponse).toHaveBeenCalledWith('Task completed', { queue: true });
  });

  it('falls back to message text when title is missing', () => {
    mockVoiceSession(LISTENING);
    renderVoiceButton();

    act(() => {
      emitVoiceBgDone('chat-1', undefined, 'Report generated.');
    });

    expect(kit.voice.speakResponse).toHaveBeenCalledWith('Report generated.', { queue: true });
  });

  it('does not announce when chat_id does not match the active chat', () => {
    mockVoiceSession(LISTENING);
    renderVoiceButton();

    act(() => {
      emitVoiceBgDone('chat-999', 'Wrong chat', 'Should be ignored.');
    });

    expect(kit.voice.speakResponse).not.toHaveBeenCalled();
  });

  it('does not announce when no title and no message', () => {
    mockVoiceSession(LISTENING);
    renderVoiceButton();

    act(() => {
      emitVoiceBgDone('chat-1', undefined, undefined);
    });

    expect(kit.voice.speakResponse).not.toHaveBeenCalled();
  });

  it('defers the announcement while the agent is speaking, then flushes after it stops', () => {
    mockVoiceSession({ sessionState: 'speaking', isActive: true });
    const { refresh } = renderVoiceButton();

    act(() => {
      emitVoiceBgDone('chat-1', 'Deferred title');
    });
    // Agent is mid-utterance: not announced yet.
    expect(kit.voice.speakResponse).not.toHaveBeenCalled();

    // Agent stops speaking → flush deferred announcement.
    mockVoiceSession(LISTENING);
    refresh();

    expect(kit.voice.speakResponse).toHaveBeenCalledWith('Deferred title', { queue: true });
  });

  it('does not register listener when voice session is inactive', () => {
    mockVoiceSession({ sessionState: 'inactive', isActive: false });
    renderVoiceButton();

    act(() => {
      emitVoiceBgDone('chat-1', 'Ignored title');
    });

    expect(kit.voice.speakResponse).not.toHaveBeenCalled();
  });

  it('still announces a notice queued before a chat switch, but ignores notices for the old chat after it', () => {
    mockVoiceSession({ sessionState: 'speaking', isActive: true });
    const { refresh } = renderVoiceButton();

    act(() => {
      emitVoiceBgDone('chat-1', 'Queued for chat-1');
    });
    expect(kit.voice.speakResponse).not.toHaveBeenCalled();

    kit.chat.chatId = 'chat-2';
    mockVoiceSession(LISTENING);
    refresh();
    expect(kit.voice.speakResponse).toHaveBeenCalledExactlyOnceWith('Queued for chat-1', { queue: true });

    act(() => {
      emitVoiceBgDone('chat-1', 'Late notice for chat-1');
    });
    expect(kit.voice.speakResponse).toHaveBeenCalledTimes(1);
  });

  it('toggles session on button click', () => {
    mockVoiceSession(LISTENING);
    renderVoiceButton();

    fireEvent.click(screen.getByRole('button'));
    expect(kit.voice.stopSession).toHaveBeenCalledOnce();
  });
});
