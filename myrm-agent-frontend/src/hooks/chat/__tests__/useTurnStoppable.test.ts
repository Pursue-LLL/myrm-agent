/** @vitest-environment jsdom */
/**
 * Stop is offered only for a turn it can reach.
 *
 * Real scenario: the user opens a chat while a turn runs on the server. For a moment the page is loading the
 * history (`loading` is true) and has not attached to the turn: Stop pressed then reaches nothing, so it must not
 * be offered until the page holds the turn's controller or the server reports the turn.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';

import { useTurnStoppable } from '../useTurnStoppable';

const CHAT_ID = 'chat-1';

beforeEach(() => {
  useChatStore.setState({ chatId: CHAT_ID, loading: false, abortController: null, sessionStatuses: {} });
  useWorkspaceStore.setState({ panes: [], activePaneId: null });
});

describe('useTurnStoppable', () => {
  it('is false while the page only loads the history of the chat', () => {
    useChatStore.setState({ loading: true });

    const { result } = renderHook(() => useTurnStoppable());

    expect(result.current).toBe(false);
  });

  it('is true once the chat-level controller of an attached or sent turn exists', () => {
    const { result } = renderHook(() => useTurnStoppable());

    act(() => useChatStore.setState({ loading: true, abortController: new AbortController() }));

    expect(result.current).toBe(true);
  });

  it('is true when only the pane that shows the chat holds the controller', () => {
    useWorkspaceStore.setState({
      panes: [
        {
          id: 'pane-1',
          chatId: CHAT_ID,
          title: 'Pane',
          snapshot: null,
          abortController: null,
          currentSessionMessageId: null,
        },
      ],
    });
    const { result } = renderHook(() => useTurnStoppable());

    act(() =>
      useWorkspaceStore.setState({
        panes: [
          {
            id: 'pane-1',
            chatId: CHAT_ID,
            title: 'Pane',
            snapshot: null,
            abortController: new AbortController(),
            currentSessionMessageId: null,
          },
        ],
      }),
    );

    expect(result.current).toBe(true);
  });

  it('ignores the controller of a pane that shows another chat', () => {
    useWorkspaceStore.setState({
      panes: [
        {
          id: 'pane-2',
          chatId: 'chat-2',
          title: 'Pane',
          snapshot: null,
          abortController: new AbortController(),
          currentSessionMessageId: null,
        },
      ],
    });

    const { result } = renderHook(() => useTurnStoppable());

    expect(result.current).toBe(false);
  });

  it('is true for a turn the server runs without a controller in this client', () => {
    const { result } = renderHook(() => useTurnStoppable());

    act(() => useChatStore.setState({ sessionStatuses: { [CHAT_ID]: 'generating' } }));

    expect(result.current).toBe(true);
  });

  it('turns false again when the turn ends and its controller is released', () => {
    useChatStore.setState({ loading: true, abortController: new AbortController() });
    const { result } = renderHook(() => useTurnStoppable());
    expect(result.current).toBe(true);

    act(() => useChatStore.setState({ loading: false, abortController: null }));

    expect(result.current).toBe(false);
  });
});
