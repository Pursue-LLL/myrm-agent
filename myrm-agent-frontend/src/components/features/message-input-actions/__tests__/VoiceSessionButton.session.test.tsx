/**
 * The headset button as a user meets it: it follows the voice settings, hands the session the right mode, turns
 * what is said into messages and reads replies aloud.
 */
import { act, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { VisualFrame } from '@/lib/vision/frameSelector';
import { expectDefined } from '@/test-utils/expectDefined';
import {
  LISTENING,
  VOICE_KEYS,
  enableVoice,
  kit,
  mockVoiceSession,
  renderVoiceButton,
  resetVoiceKit,
  voiceOptions,
} from './voiceSessionKit';

describe('VoiceSessionButton', () => {
  beforeEach(resetVoiceKit);

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('voice settings', () => {
    it('renders nothing until voice sessions are enabled', () => {
      const { container } = renderVoiceButton();

      expect(container).toBeEmptyDOMElement();
    });

    it('offers to start a session, and to stop it while one runs', () => {
      enableVoice();
      const { refresh } = renderVoiceButton();
      expect(screen.getByRole('button', { name: 'startSession' })).toBeInTheDocument();

      mockVoiceSession(LISTENING);
      refresh();

      expect(screen.getByRole('button', { name: 'stopSession' })).toBeInTheDocument();
    });

    it('picks up a setting changed in another tab', () => {
      const { container } = renderVoiceButton();
      expect(container).toBeEmptyDOMElement();

      act(() => {
        enableVoice();
        window.dispatchEvent(new StorageEvent('storage'));
      });

      expect(screen.getByRole('button', { name: 'startSession' })).toBeInTheDocument();
    });

    it('treats storage the browser refuses as "not enabled" instead of crashing', () => {
      const refuse = () => {
        throw new DOMException('blocked', 'SecurityError');
      };
      vi.stubGlobal('localStorage', { getItem: refuse, setItem: refuse, removeItem: refuse });

      const { container } = renderVoiceButton();

      expect(container).toBeEmptyDOMElement();
      expect(voiceOptions()).toMatchObject({ enabled: false, mode: 'audio_only', fullDuplex: true });
    });

    it.each([
      { mode: 'audio_only', bridge: undefined, expected: 'audio_only' },
      { mode: 'agent_bridge', bridge: undefined, expected: 'agent_bridge' },
      { mode: 'openai_realtime', bridge: undefined, expected: 'openai_realtime' },
      { mode: 'gemini_live', bridge: undefined, expected: 'gemini_live' },
      { mode: undefined, bridge: 'true', expected: 'agent_bridge' },
      { mode: undefined, bridge: 'false', expected: 'audio_only' },
      { mode: undefined, bridge: undefined, expected: 'audio_only' },
      { mode: 'agent_bridge', bridge: 'false', expected: 'agent_bridge' },
      { mode: 'warp', bridge: 'true', expected: 'agent_bridge' },
      { mode: 'toString', bridge: undefined, expected: 'audio_only' },
    ])('runs $expected for saved mode $mode and bridge switch $bridge', ({ mode, bridge, expected }) => {
      enableVoice();
      if (mode) {
        localStorage.setItem(VOICE_KEYS.mode, mode);
      }
      if (bridge) {
        localStorage.setItem(VOICE_KEYS.agentBridge, bridge);
      }

      renderVoiceButton();

      expect(voiceOptions().mode).toBe(expected);
    });

    it.each([
      { saved: undefined, expected: true },
      { saved: 'true', expected: true },
      { saved: 'false', expected: false },
      { saved: 'off', expected: true },
    ])('keeps full duplex $expected when it is saved as $saved', ({ saved, expected }) => {
      enableVoice(saved === undefined ? {} : { fullDuplex: saved });

      renderVoiceButton();

      expect(voiceOptions().fullDuplex).toBe(expected);
    });

    it('gives the session the active agent and chat and the caller key terms', () => {
      enableVoice();
      kit.chat.agentConfig = { agentId: 'agent-7' };
      kit.chat.chatId = 'chat-9';

      renderVoiceButton({ keyterms: ['alpha'] });

      expect(voiceOptions()).toMatchObject({
        enabled: true,
        autoSend: true,
        agentId: 'agent-7',
        chatId: 'chat-9',
        keyterms: ['alpha'],
      });
    });

    it('leaves the agent and chat out when there are none', () => {
      enableVoice();
      kit.chat.chatId = null;

      renderVoiceButton();

      expect(voiceOptions().agentId).toBeUndefined();
      expect(voiceOptions().chatId).toBeUndefined();
    });
  });

  describe('messages from the session', () => {
    const frame = (base64: string): VisualFrame => ({ id: base64, base64, width: 1, height: 1, timestamp: 0 });

    function say(text: string, frames?: VisualFrame[]) {
      enableVoice();
      renderVoiceButton();
      const onSendMessage = voiceOptions().onSendMessage;
      expectDefined(onSendMessage, 'onSendMessage');
      onSendMessage(text, frames);
    }

    it('sends what was said', () => {
      say('hello there');

      expect(kit.chat.sendMessage).toHaveBeenCalledExactlyOnceWith('hello there');
      expect(kit.chat.setCameraFrames).not.toHaveBeenCalled();
    });

    it('ignores blank speech', () => {
      say('   ');

      expect(kit.chat.sendMessage).not.toHaveBeenCalled();
    });

    it('hands over camera frames as data URLs before the message, completing bare base64', () => {
      say('what is this', [frame('AAA'), frame('data:image/png;base64,BBB')]);

      expect(kit.chat.setCameraFrames).toHaveBeenCalledExactlyOnceWith([
        'data:image/jpeg;base64,AAA',
        'data:image/png;base64,BBB',
      ]);
      expect(kit.chat.setCameraFrames.mock.invocationCallOrder[0]).toBeLessThan(
        kit.chat.sendMessage.mock.invocationCallOrder[0],
      );
    });

    it('sends no camera frames when the list is empty', () => {
      say('just words', []);

      expect(kit.chat.setCameraFrames).not.toHaveBeenCalled();
      expect(kit.chat.sendMessage).toHaveBeenCalledWith('just words');
    });
  });

  describe('reading replies aloud', () => {
    const reply = (content: string, messageId?: string) => ({ role: 'assistant', content, messageId });

    beforeEach(() => {
      enableVoice();
      mockVoiceSession(LISTENING);
    });

    it('speaks a new reply once the turn is done, and never the same text twice', () => {
      kit.chat.messages = [reply('The first full answer')];
      const { refresh } = renderVoiceButton();
      expect(kit.voice.speakResponse).toHaveBeenCalledExactlyOnceWith('The first full answer');

      kit.chat.messages = [reply('The first full answer')];
      refresh();
      expect(kit.voice.speakResponse).toHaveBeenCalledTimes(1);

      kit.chat.messages = [reply('A different second answer')];
      refresh();
      expect(kit.voice.speakResponse).toHaveBeenCalledTimes(2);
      expect(kit.voice.speakResponse).toHaveBeenLastCalledWith('A different second answer');
    });

    it('speaks a reply from eleven characters up', () => {
      kit.chat.messages = [reply('Eleven char')];

      renderVoiceButton();

      expect(kit.voice.speakResponse).toHaveBeenCalledWith('Eleven char');
    });

    it.each([
      {
        when: 'the reply is still streaming',
        arrange: () => {
          kit.chat.loading = true;
          kit.chat.messages = [reply('A long enough reply')];
        },
      },
      {
        when: 'the reply announces a finished background task, which has its own spoken notice',
        arrange: () => {
          kit.chat.messages = [reply('A long enough reply', 'voice_bg_done_1')];
        },
      },
      {
        when: 'the last message is from the user',
        arrange: () => {
          kit.chat.messages = [{ role: 'user', content: 'A long enough question' }];
        },
      },
      {
        when: 'there is no message yet',
        arrange: () => {
          kit.chat.messages = [];
        },
      },
      {
        when: 'the reply is ten characters or fewer',
        arrange: () => {
          kit.chat.messages = [reply('Ten chars!')];
        },
      },
      {
        when: 'no session is running',
        arrange: () => {
          mockVoiceSession();
          kit.chat.messages = [reply('A long enough reply')];
        },
      },
    ])('stays silent when $when', ({ arrange }) => {
      arrange();

      renderVoiceButton();

      expect(kit.voice.speakResponse).not.toHaveBeenCalled();
    });

    it('stays silent when the session streams the agent audio itself', () => {
      localStorage.setItem(VOICE_KEYS.mode, 'agent_bridge');
      kit.chat.messages = [reply('A long enough reply')];
      // Settings are read right after mount, and no session can be running before that.
      mockVoiceSession();
      const { refresh } = renderVoiceButton();

      mockVoiceSession(LISTENING);
      refresh();

      expect(kit.voice.speakResponse).not.toHaveBeenCalled();
    });
  });
});
