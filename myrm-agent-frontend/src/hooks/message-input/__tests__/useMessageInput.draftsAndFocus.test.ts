import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  buildChatState,
  chatStoreRef,
  mockAddInputHistory,
  mockSendMessage,
  mockUseDraftPersistence,
  resetMessageInputMocks,
} from './messageInputKit';

describe('useMessageInput drafts, input history and the focus shortcut', () => {
  beforeEach(resetMessageInputMocks);

  describe('incognito sessions', () => {
    it('keeps drafts and input history off disk', async () => {
      chatStoreRef.state = buildChatState({ incognitoMode: true });
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
      });

      expect(mockUseDraftPersistence).toHaveBeenCalledWith(null, expect.any(String));
      expect(mockAddInputHistory).not.toHaveBeenCalled();
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    it('persists drafts and input history in regular sessions', async () => {
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
      });

      expect(mockUseDraftPersistence).toHaveBeenCalledWith('chat-test', expect.any(String));
      expect(mockAddInputHistory).toHaveBeenCalledTimes(1);
    });
  });

  describe('the / shortcut that jumps to the input', () => {
    /** Mounts the hook with a stand-in input, and a second element holding the focus. */
    async function mountWithFocusElsewhere(focusHolder: () => HTMLElement) {
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());
      const input = document.body.appendChild(document.createElement('textarea'));
      result.current.inputRef.current = input;
      const holder = focusHolder();
      holder.tabIndex = 0;
      holder.focus();
      return { input, holder };
    }

    const pressSlash = () => {
      const event = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true });
      document.activeElement?.dispatchEvent(event);
      return event;
    };

    afterEach(() => {
      document.body.replaceChildren();
    });

    it('moves the focus to the input when nothing is being typed into', async () => {
      const { input } = await mountWithFocusElsewhere(() => document.body.appendChild(document.createElement('div')));

      const event = pressSlash();

      expect(event.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(input);
    });

    it('leaves the slash alone in a code editor, where it is text: Monaco focuses a plain div', async () => {
      const { input, holder } = await mountWithFocusElsewhere(() => {
        const editor = document.body.appendChild(document.createElement('div'));
        editor.className = 'monaco-editor';
        return editor.appendChild(document.createElement('div'));
      });

      const event = pressSlash();

      expect(event.defaultPrevented).toBe(false);
      expect(document.activeElement).toBe(holder);
      expect(document.activeElement).not.toBe(input);
    });
  });
});
