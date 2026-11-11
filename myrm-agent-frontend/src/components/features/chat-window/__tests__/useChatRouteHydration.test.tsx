/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { beforeEach, describe, expect, it } from 'vitest';

import type { ChatState, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

import { useChatRouteHydration } from '../useChatRouteHydration';

type HydrationState = Pick<ChatState, 'chatId' | 'isMessagesLoaded' | 'messages' | 'compactedSummary'>;

const message = (chatId: string): Message => ({
  messageId: 'm-1',
  chatId,
  createdAt: new Date(0),
  content: 'hello',
  role: 'user',
});

const emptyStore: HydrationState = { chatId: undefined, isMessagesLoaded: false, messages: [], compactedSummary: null };

/** The store state of a conversation that finished loading. */
const loaded = (chatId = 'chat-1', overrides: Partial<HydrationState> = {}): HydrationState => ({
  chatId,
  isMessagesLoaded: true,
  messages: [message(chatId)],
  compactedSummary: null,
  ...overrides,
});

const signalE2eHydration = (detail?: { chatId?: string }) =>
  act(() => {
    window.dispatchEvent(new CustomEvent('myrm-e2e-chat-route-hydrated', { detail }));
  });

function HydrationProbe({ id }: { id: string }) {
  const { chatRouteHydrated } = useChatRouteHydration(id);
  return <span>{`hydrated:${chatRouteHydrated}`}</span>;
}

describe('useChatRouteHydration', () => {
  beforeEach(() => {
    useChatStore.setState(emptyStore);
  });

  describe('whether the conversation is hydrated', () => {
    it('is hydrated once the store holds the loaded messages of the conversation', () => {
      useChatStore.setState(loaded());

      const { result } = renderHook(() => useChatRouteHydration('chat-1'));

      expect(result.current.chatRouteHydrated).toBe(true);
      expect(result.current.chatMessagesForRender).toHaveLength(1);
    });

    it('counts a conversation that only has a compacted summary as hydrated', () => {
      useChatStore.setState(loaded('chat-1', { messages: [], compactedSummary: 'Earlier, we agreed on the plan.' }));

      const { result } = renderHook(() => useChatRouteHydration('chat-1'));

      expect(result.current.chatRouteHydrated).toBe(true);
    });

    it.each<{ name: string; state: Partial<HydrationState> }>([
      { name: 'the store holds another conversation', state: { chatId: 'chat-2' } },
      { name: 'its messages are still loading', state: { isMessagesLoaded: false } },
      { name: 'it has neither messages nor a summary', state: { messages: [] } },
      { name: 'its only summary is blank', state: { messages: [], compactedSummary: '   ' } },
    ])('is not hydrated when $name', ({ state }) => {
      useChatStore.setState(loaded('chat-1', state));

      const { result } = renderHook(() => useChatRouteHydration('chat-1'));

      expect(result.current.chatRouteHydrated).toBe(false);
    });

    it('is never hydrated without a conversation id, whatever the store holds', () => {
      useChatStore.setState(loaded());

      const { result } = renderHook(() => useChatRouteHydration(undefined));

      expect(result.current.chatRouteHydrated).toBe(false);
    });

    it('answers "not hydrated" in server markup even when the store already holds the conversation', () => {
      useChatStore.setState(loaded());

      // The client trusts the store straight away, but the server render has to agree with the first client render.
      expect(renderToString(<HydrationProbe id="chat-1" />)).toContain('hydrated:false');
      const { result } = renderHook(() => useChatRouteHydration('chat-1'));
      expect(result.current.chatRouteHydrated).toBe(true);
    });
  });

  describe('the chat view rebuild epoch', () => {
    it('advances when the hydration answer flips, and only then', () => {
      const { result } = renderHook(() => useChatRouteHydration('chat-1'));
      expect(result.current.routeHydrationEpoch).toBe(0);

      act(() => useChatStore.setState(loaded()));
      expect(result.current.routeHydrationEpoch).toBe(1);

      act(() => useChatStore.setState({ inputMessage: 'a store write that leaves hydration alone' }));
      expect(result.current.routeHydrationEpoch).toBe(1);

      act(() => useChatStore.setState({ messages: [] }));
      expect(result.current.routeHydrationEpoch).toBe(2);
    });

    it('advances on the end-to-end hydration signal for its own conversation', () => {
      const { result } = renderHook(() => useChatRouteHydration('chat-1'));

      signalE2eHydration({ chatId: 'chat-1' });

      expect(result.current.routeHydrationEpoch).toBe(1);
    });

    it('ignores the signal for another conversation, and a signal that names none', () => {
      const { result } = renderHook(() => useChatRouteHydration('chat-1'));

      signalE2eHydration({ chatId: 'chat-2' });
      signalE2eHydration();

      expect(result.current.routeHydrationEpoch).toBe(0);
    });

    it('does not listen for the signal without a conversation id', () => {
      const { result } = renderHook(() => useChatRouteHydration(undefined));

      signalE2eHydration({});

      expect(result.current.routeHydrationEpoch).toBe(0);
    });
  });
});
