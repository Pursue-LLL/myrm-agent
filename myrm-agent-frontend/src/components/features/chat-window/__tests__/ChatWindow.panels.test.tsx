/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindow (POS: 聊天窗口，按路由与 store 状态编排横幅、面板与聊天视图)
 * - ./chatWindowMocks (POS: 子组件探针与路由替身)
 *
 * [OUTPUT]
 * Vitest: 404 / 加载失败视图、主页与会话两种布局、目标面板开关、聊天与轨迹双 Tab 下的面板归属、
 * 顾问面板的打开与复位、待审批记忆徽章的去向、E2E 水合事件对聊天视图的重建、扩展 UI 会话 id 与配置加载。
 *
 * [POS]
 * 子组件为探针，窗口、聊天 / 记忆 / 特性开关 store 为真实实现。
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation, openChatInStore } from './chatWindowMocks';
import type { ChatState, Message } from '@/store/chat/types';
import type { PendingMemory } from '@/store/memory/types';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useExtensionUIStore } from '@/store/useExtensionUIStore';
import { useMemoryStore } from '@/store/memory';
import ChatWindow from '../ChatWindow';

const OPEN_CHAT = 'chat-panels-1';
const FIRST_MESSAGE = {
  messageId: 'm-1',
  chatId: OPEN_CHAT,
  role: 'user',
  content: 'hi',
  createdAt: new Date(),
} as Message;

function pendingMemory(id: string): PendingMemory {
  return { id } as unknown as PendingMemory;
}

function enableGoals(): void {
  useFeatureGateStore.setState({ enabledFeatures: new Set(['goals_system']) });
}

beforeEach(() => {
  vi.clearAllMocks();
  navigation.searchParams = new URLSearchParams();
  useFeatureGateStore.setState({ enabledFeatures: new Set() });
  useMemoryStore.setState({ pendingMemories: [], conflictCount: 0, openConfirmDialog: vi.fn() });
  openChatInStore(OPEN_CHAT, { messages: [FIRST_MESSAGE] });
});

describe('ChatWindow error views', () => {
  it('shows the 404 page for a chat that does not exist', () => {
    openChatInStore(OPEN_CHAT, { notFound: true });
    render(<ChatWindow id={OPEN_CHAT} />);

    expect(screen.getByTestId('next-error').textContent).toBe('404');
    expect(screen.queryByTestId('chat')).toBeNull();
  });

  it('shows the connection error with a way to the settings when loading failed', () => {
    openChatInStore(OPEN_CHAT, { loadError: true });
    render(<ChatWindow id={OPEN_CHAT} />);

    expect(screen.getByText('connectionFailed')).toBeTruthy();
    expect(document.querySelector('a[href="/settings"]')).not.toBeNull();
    expect(screen.queryByTestId('chat')).toBeNull();
  });

  it('prefers the 404 page when both flags are set', () => {
    openChatInStore(OPEN_CHAT, { notFound: true, loadError: true });
    render(<ChatWindow id={OPEN_CHAT} />);

    expect(screen.getByTestId('next-error')).toBeTruthy();
    expect(screen.queryByText('connectionFailed')).toBeNull();
  });
});

describe('ChatWindow layouts', () => {
  it('shows the chat view for a route with a chat id', () => {
    render(<ChatWindow id={OPEN_CHAT} />);

    expect(screen.getByTestId('chat')).toBeTruthy();
    expect(screen.queryByTestId('empty-chat')).toBeNull();
    expect(screen.getByTestId('satellites').getAttribute('data-chat')).toBe(OPEN_CHAT);
    expect(useExtensionUIStore.getState().chatId).toBe(OPEN_CHAT);
  });

  it('shows the empty chat on home and keeps the chat-bound panels away', () => {
    openChatInStore('c-held-for-home');
    render(<ChatWindow />);

    expect(screen.getByTestId('empty-chat')).toBeTruthy();
    expect(screen.queryByTestId('chat')).toBeNull();
    expect(screen.queryByTestId('advisor')).toBeNull();
    expect(screen.getByTestId('satellites').getAttribute('data-chat')).toBe('');
    expect(useExtensionUIStore.getState().chatId).toBeNull();
  });

  it('switches home to the chat view once messages arrive, without a session advisor', () => {
    openChatInStore('c-held-for-home');
    render(<ChatWindow />);
    expect(screen.getByTestId('empty-chat')).toBeTruthy();

    act(() => {
      useChatStore.setState({ messages: [FIRST_MESSAGE] });
    });

    expect(screen.getByTestId('chat')).toBeTruthy();
    expect(screen.queryByTestId('empty-chat')).toBeNull();
    expect(screen.queryByTestId('advisor')).toBeNull();
  });

  it('re-creates the chat view when a loaded conversation is reloaded in place', () => {
    render(<ChatWindow id={OPEN_CHAT} />);
    const before = screen.getByTestId('chat');

    // Hydration flips off and on again within one batch: label and message count end up as they were.
    act(() => {
      useChatStore.setState({ isMessagesLoaded: false });
      useChatStore.setState({ isMessagesLoaded: true });
    });

    expect(screen.getByTestId('chat')).not.toBe(before);
  });

  it('loads the configuration once when it appears', () => {
    render(<ChatWindow id={OPEN_CHAT} />);

    expect(useConfigStore.getState().initConfig).toHaveBeenCalledOnce();
  });

  it('covers the chat with a skeleton only until its messages are in', () => {
    openChatInStore(OPEN_CHAT, { isMessagesLoaded: false, messages: [] });
    const { unmount } = render(<ChatWindow id={OPEN_CHAT} />);
    expect(screen.getByTestId('skeleton')).toBeTruthy();
    unmount();

    openChatInStore(OPEN_CHAT, { messages: [FIRST_MESSAGE] });
    render(<ChatWindow id={OPEN_CHAT} />);
    expect(screen.queryByTestId('skeleton')).toBeNull();
  });

  describe('goals', () => {
    it('adds the goal card to a chat and the goal control plane to home when goals are enabled', () => {
      enableGoals();
      const { unmount } = render(<ChatWindow id={OPEN_CHAT} />);
      expect(screen.getByTestId('goal-status-card')).toBeTruthy();
      expect(screen.queryByTestId('goal-control-plane')).toBeNull();
      unmount();

      openChatInStore('c-held-for-home');
      render(<ChatWindow />);
      expect(screen.getByTestId('goal-status-card')).toBeTruthy();
      expect(screen.getByTestId('goal-control-plane')).toBeTruthy();
    });

    it('shows neither when goals are not enabled', () => {
      const { unmount } = render(<ChatWindow id={OPEN_CHAT} />);
      expect(screen.queryByTestId('goal-status-card')).toBeNull();
      unmount();

      openChatInStore('c-held-for-home');
      render(<ChatWindow />);
      expect(screen.queryByTestId('goal-status-card')).toBeNull();
      expect(screen.queryByTestId('goal-control-plane')).toBeNull();
    });
  });
});

describe('ChatWindow chat and trace tabs', () => {
  it('shows the agent banner only while an agent is applied', () => {
    const { unmount } = render(<ChatWindow id={OPEN_CHAT} />);
    expect(screen.queryByTestId('agent-banner')).toBeNull();
    unmount();

    openChatInStore(OPEN_CHAT, {
      messages: [FIRST_MESSAGE],
      agentConfig: { agentId: 'agent-9' } as unknown as ChatState['agentConfig'],
    });
    render(<ChatWindow id={OPEN_CHAT} />);
    expect(screen.getByTestId('agent-banner').textContent).toBe('agent-9');
  });

  it('keeps the delivery panel and memory banner on the chat tab only', () => {
    render(<ChatWindow id={OPEN_CHAT} />);
    expect(screen.getByTestId('five-contract')).toBeTruthy();
    expect(screen.getByTestId('memory-conflict-banner')).toBeTruthy();

    fireEvent.click(screen.getByText('dualTabTrace'));

    expect(screen.queryByTestId('five-contract')).toBeNull();
    expect(screen.queryByTestId('memory-conflict-banner')).toBeNull();
    expect(screen.queryByTestId('chat')).toBeNull();
  });

  it('polls the execution trace every 2 seconds only while a turn is running', () => {
    render(<ChatWindow id={OPEN_CHAT} />);
    fireEvent.click(screen.getByText('dualTabTrace'));
    expect(screen.getByTestId('trace').textContent).toBe(OPEN_CHAT);
    expect(screen.getByTestId('trace').getAttribute('data-poll')).toBe('undefined');

    act(() => useChatStore.setState({ loading: true }));
    expect(screen.getByTestId('trace').getAttribute('data-poll')).toBe('2000');
  });
});

describe('ChatWindow session advisor', () => {
  it('opens with the question and selection of the event, and resets both when closed', () => {
    render(<ChatWindow id={OPEN_CHAT} />);
    expect(screen.getByTestId('advisor').getAttribute('data-open')).toBe('false');

    act(() => {
      window.dispatchEvent(
        new CustomEvent('copilot-open-advisor', { detail: { question: 'why this?', selection: 'a snippet' } }),
      );
    });
    const open = screen.getByTestId('advisor');
    expect([open.dataset.open, open.dataset.question, open.dataset.selection]).toEqual([
      'true',
      'why this?',
      'a snippet',
    ]);

    fireEvent.click(screen.getByText('close advisor'));
    const closed = screen.getByTestId('advisor');
    expect([closed.dataset.open, closed.dataset.question, closed.dataset.selection]).toEqual(['false', '', '']);
  });

  it('opens empty when the event carries no detail', () => {
    render(<ChatWindow id={OPEN_CHAT} />);

    act(() => {
      window.dispatchEvent(new CustomEvent('copilot-open-advisor'));
    });

    const advisor = screen.getByTestId('advisor');
    expect([advisor.dataset.open, advisor.dataset.question, advisor.dataset.selection]).toEqual(['true', '', '']);
  });
});

describe('ChatWindow pending memory badge', () => {
  it('sends the user to the pending tab of the memory settings while conflicts exist', () => {
    const openConfirmDialog = vi.fn();
    useMemoryStore.setState({ conflictCount: 2, pendingMemories: [pendingMemory('pm-1')], openConfirmDialog });
    render(<ChatWindow id={OPEN_CHAT} />);

    fireEvent.click(screen.getByText('pending memory badge'));

    expect(navigation.push).toHaveBeenCalledExactlyOnceWith('/settings/memory?tab=pending');
    expect(openConfirmDialog).not.toHaveBeenCalled();
  });

  it('opens the confirmation of the oldest pending memory when there are no conflicts', () => {
    const openConfirmDialog = vi.fn();
    const oldest = pendingMemory('pm-1');
    useMemoryStore.setState({ pendingMemories: [oldest, pendingMemory('pm-2')], openConfirmDialog });
    render(<ChatWindow id={OPEN_CHAT} />);

    fireEvent.click(screen.getByText('pending memory badge'));

    expect(openConfirmDialog).toHaveBeenCalledExactlyOnceWith(oldest);
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it('does nothing when nothing is pending', () => {
    const openConfirmDialog = vi.fn();
    useMemoryStore.setState({ openConfirmDialog });
    render(<ChatWindow id={OPEN_CHAT} />);

    fireEvent.click(screen.getByText('pending memory badge'));

    expect(openConfirmDialog).not.toHaveBeenCalled();
    expect(navigation.push).not.toHaveBeenCalled();
  });
});

describe('ChatWindow end-to-end hydration signal', () => {
  function signalHydrated(chatId: string): void {
    act(() => {
      window.dispatchEvent(new CustomEvent('myrm-e2e-chat-route-hydrated', { detail: { chatId } }));
    });
  }

  it('re-creates the chat view when the signal names the open chat', () => {
    render(<ChatWindow id={OPEN_CHAT} />);
    const before = screen.getByTestId('chat');

    signalHydrated(OPEN_CHAT);

    expect(screen.getByTestId('chat')).not.toBe(before);
  });

  it('leaves the chat view alone for the signal of another chat', () => {
    render(<ChatWindow id={OPEN_CHAT} />);
    const before = screen.getByTestId('chat');

    signalHydrated('another-chat');

    expect(screen.getByTestId('chat')).toBe(before);
  });
});
