/**
 * The running session as a user sees it: the spoken stop command, the overlay and its minimised bubble, and the
 * remote controls the pet surface sends.
 */
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { LISTENING, enableVoice, kit, mockVoiceSession, renderVoiceButton, resetVoiceKit } from './voiceSessionKit';

describe('VoiceSessionButton session', () => {
  beforeEach(resetVoiceKit);

  describe('spoken stop command', () => {
    it('ends the session once, however often the transcript repeats it', () => {
      enableVoice();
      mockVoiceSession({ ...LISTENING, interimText: 'Stop.' });
      const { refresh } = renderVoiceButton();
      expect(kit.voice.stopSession).toHaveBeenCalledTimes(1);

      refresh();

      expect(kit.voice.stopSession).toHaveBeenCalledTimes(1);
    });

    it('listens for it again in the next session', () => {
      enableVoice();
      mockVoiceSession({ ...LISTENING, interimText: 'stop' });
      const { refresh } = renderVoiceButton();

      mockVoiceSession();
      refresh();
      mockVoiceSession({ ...LISTENING, interimText: 'stop' });
      refresh();

      expect(kit.voice.stopSession).toHaveBeenCalledTimes(2);
    });

    it.each([
      { case: 'the word sits inside a sentence', state: { ...LISTENING, interimText: 'please stop the music' } },
      { case: 'no session is running', state: { interimText: 'stop' } },
    ])('does nothing when $case', ({ state }) => {
      enableVoice();
      mockVoiceSession(state);

      renderVoiceButton();

      expect(kit.voice.stopSession).not.toHaveBeenCalled();
    });
  });

  describe('session window', () => {
    it('starts a session from the button and stops it from the same button', () => {
      enableVoice();
      const { refresh } = renderVoiceButton();

      fireEvent.click(screen.getByRole('button'));
      expect(kit.voice.startSession).toHaveBeenCalledTimes(1);

      mockVoiceSession(LISTENING);
      refresh();
      fireEvent.click(screen.getByRole('button'));
      expect(kit.voice.stopSession).toHaveBeenCalledTimes(1);
    });

    it('disables the button while the composer is disabled', () => {
      enableVoice();
      renderVoiceButton({ disabled: true });

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('opens the overlay for a running session, folds it into the bubble when minimised, and opens it again from the bubble', () => {
      enableVoice();
      mockVoiceSession(LISTENING);
      renderVoiceButton();
      expect(kit.overlayProps?.isOpen).toBe(true);
      expect(kit.bubbleProps?.visible).toBe(false);

      act(() => kit.overlayProps?.onMinimize?.());
      expect(kit.overlayProps?.isOpen).toBe(false);
      expect(kit.bubbleProps?.visible).toBe(true);

      act(() => kit.bubbleProps?.onExpand());
      expect(kit.overlayProps?.isOpen).toBe(true);
      expect(kit.bubbleProps?.visible).toBe(false);
    });

    it('opens the overlay again for the next session after one ended while minimised', () => {
      enableVoice();
      mockVoiceSession(LISTENING);
      const { refresh } = renderVoiceButton();
      act(() => kit.overlayProps?.onMinimize?.());

      mockVoiceSession();
      refresh();
      mockVoiceSession(LISTENING);
      refresh();

      expect(kit.overlayProps?.isOpen).toBe(true);
    });

    it('closes and interrupts through the session', () => {
      enableVoice();
      mockVoiceSession(LISTENING);
      renderVoiceButton();

      kit.overlayProps?.onClose();
      kit.overlayProps?.onInterrupt();

      expect(kit.voice.stopSession).toHaveBeenCalledTimes(1);
      expect(kit.voice.interruptTTS).toHaveBeenCalledTimes(1);
    });

    it('tells the overlay about the agent bridge and the mode', () => {
      enableVoice({ mode: 'agent_bridge' });
      mockVoiceSession(LISTENING);

      renderVoiceButton();

      expect(kit.overlayProps).toMatchObject({ isAgentBridge: true, voiceMode: 'agent_bridge' });
    });

    it.each([
      { state: { agentToolName: 'web_search', interimText: 'hi' }, text: 'web_search' },
      { state: { agentToolName: '', interimText: 'hi' }, text: 'hi' },
    ])('shows "$text" in the bubble', ({ state, text }) => {
      enableVoice();
      mockVoiceSession({ ...LISTENING, ...state });

      renderVoiceButton();

      expect(kit.bubbleProps?.statusText).toBe(text);
    });

    it('marks the bubble as speaking only while the agent speaks', () => {
      enableVoice();
      mockVoiceSession({ sessionState: 'speaking', isActive: true });
      const { refresh } = renderVoiceButton();
      expect(kit.bubbleProps?.speaking).toBe(true);

      mockVoiceSession(LISTENING);
      refresh();

      expect(kit.bubbleProps?.speaking).toBe(false);
    });
  });

  describe('remote controls from the pet surface', () => {
    const emit = (name: string) =>
      act(() => {
        window.dispatchEvent(new CustomEvent(name));
      });

    it('toggles the session', () => {
      enableVoice();
      const { refresh } = renderVoiceButton();

      emit('myrm-voice-toggle');
      expect(kit.voice.startSession).toHaveBeenCalledTimes(1);

      mockVoiceSession(LISTENING);
      refresh();
      emit('myrm-voice-toggle');
      expect(kit.voice.stopSession).toHaveBeenCalledTimes(1);
    });

    it('interrupts speech only while a session runs', () => {
      enableVoice();
      const { refresh } = renderVoiceButton();
      emit('myrm-voice-interrupt');
      expect(kit.voice.interruptTTS).not.toHaveBeenCalled();

      mockVoiceSession(LISTENING);
      refresh();
      emit('myrm-voice-interrupt');

      expect(kit.voice.interruptTTS).toHaveBeenCalledTimes(1);
    });

    it('replays the last spoken text', async () => {
      enableVoice();
      mockVoiceSession(LISTENING);
      kit.lastSpokenText.mockReturnValue('Last words');
      renderVoiceButton();

      emit('myrm-voice-replay');

      await waitFor(() => expect(kit.voice.speakResponse).toHaveBeenCalledWith('Last words'));
    });

    it('replays nothing when nothing was spoken yet', async () => {
      enableVoice();
      mockVoiceSession(LISTENING);
      renderVoiceButton();

      emit('myrm-voice-replay');

      await waitFor(() => expect(kit.lastSpokenText).toHaveBeenCalled());
      expect(kit.voice.speakResponse).not.toHaveBeenCalled();
    });

    it('stops answering once the button is gone', () => {
      enableVoice();
      const { unmount } = renderVoiceButton();
      unmount();

      emit('myrm-voice-toggle');

      expect(kit.voice.startSession).not.toHaveBeenCalled();
    });

    it('tells the pet surface what the session is doing', () => {
      const updates: Array<{ voiceState: string; audioLevel: number }> = [];
      const listener = (event: Event) => updates.push((event as CustomEvent<(typeof updates)[number]>).detail);
      window.addEventListener('myrm-voice-state-update', listener);
      enableVoice();
      const { refresh } = renderVoiceButton();

      mockVoiceSession({ sessionState: 'listening', isActive: true, audioLevel: 0.5 });
      refresh();
      window.removeEventListener('myrm-voice-state-update', listener);

      expect(updates).toEqual([
        { voiceState: 'idle', audioLevel: 0 },
        { voiceState: 'listening', audioLevel: 0.5 },
      ]);
    });
  });
});
