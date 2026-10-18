/** @vitest-environment jsdom */
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import ChatWindow from '../ChatWindow';

const navigationMock = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  prefetch: vi.fn(),
  searchParams: new URLSearchParams(),
}));
const chatView = vi.hoisted(() => ({ mounts: 0 }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: navigationMock.replace,
    push: navigationMock.push,
    prefetch: navigationMock.prefetch,
  }),
  useSearchParams: () => navigationMock.searchParams,
  usePathname: () => '/',
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

// A mount is what costs the user their composer focus and repeats every fetch that runs when the view appears.
vi.mock('../Chat', async () => {
  const { useEffect } = await import('react');
  function ChatProbe() {
    useEffect(() => {
      chatView.mounts += 1;
    }, []);
    return <div data-testid="chat" />;
  }
  return { default: ChatProbe };
});
vi.mock('../EmptyChat', () => ({ default: () => <textarea aria-label="message input" /> }));
vi.mock('../MessageListSkeleton', () => ({ default: () => <div>skeleton</div> }));
vi.mock('../ToolApprovalDialog', () => ({ default: () => null }));
vi.mock('../ToolApprovalExpiryWatcher', () => ({ default: () => null }));
vi.mock('../AgentInfoBanner', () => ({ default: () => null }));
vi.mock('../YoloModeBanner', () => ({ default: () => null }));
vi.mock('../EStopBanner', () => ({ default: () => null }));
vi.mock('../ExtensionDisconnectedBanner', () => ({ default: () => null }));
vi.mock('../ExtensionTakeoverBanner', () => ({ default: () => null }));
vi.mock('../ChatWindowSatellites', () => ({
  default: () => null,
  GoalControlPlane: () => null,
  GoalStatusCard: () => null,
  LifeStatusCapsule: () => null,
}));
vi.mock('../ParentChatLink', () => ({ ParentChatLink: () => null }));
vi.mock('../ChatCronLink', () => ({ ChatCronLink: () => null }));
vi.mock('../WorkingStateBadge', () => ({ default: () => null }));
vi.mock('../SubagentPromptButton', () => ({ default: () => null }));
vi.mock('../subagent/SubagentDashboard', () => ({ default: () => null }));
vi.mock('../artifacts/ArtifactPortal', () => ({ default: () => null }));
vi.mock('@/components/features/app-shell/VisualDesktopToggle', () => ({ VisualDesktopToggle: () => null }));
vi.mock('@/components/features/message-actions/SessionRevertButton', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/RunStatusChip', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/SessionAdvisorPanel', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryBadge', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryDialog', () => ({ default: () => null }));

const CHAT_ID = 'session-remount-1';
const FIRST_MESSAGE = { id: 'msg-1', role: 'user', content: 'hello' } as unknown as Message;

describe('ChatWindow keeps the chat view mounted', () => {
  beforeEach(() => {
    chatView.mounts = 0;
    navigationMock.searchParams = new URLSearchParams();
    useChatStore.setState({
      chatId: CHAT_ID,
      inputMessage: '',
      messages: [FIRST_MESSAGE],
      isMessagesLoaded: true,
      loading: false,
      messageAppeared: true,
      notFound: false,
      loadError: false,
      activeKnowledgeBaseIds: [],
      activeKnowledgeBaseNames: {},
    });
  });

  it('does not re-create the view for store writes that do not change what it shows', () => {
    render(<ChatWindow id={CHAT_ID} />);
    const mountsAfterRender = chatView.mounts;
    expect(mountsAfterRender).toBeGreaterThan(0);

    // Every key typed in the composer and every mount-time sync of the knowledge-base selection is a store write.
    for (const typed of ['h', 'he', 'hel']) {
      act(() => useChatStore.setState({ inputMessage: typed }));
    }
    for (let sync = 0; sync < 3; sync += 1) {
      act(() => useChatStore.setState({ activeKnowledgeBaseIds: [], activeKnowledgeBaseNames: {} }));
    }

    expect(chatView.mounts).toBe(mountsAfterRender);
  });

  it('re-creates the view once when the conversation finishes loading, not again for later writes', () => {
    useChatStore.setState({ messages: [], isMessagesLoaded: false });
    render(<ChatWindow id={CHAT_ID} />);
    const mountsBeforeLoad = chatView.mounts;

    act(() => useChatStore.setState({ messages: [FIRST_MESSAGE], isMessagesLoaded: true }));
    expect(chatView.mounts).toBe(mountsBeforeLoad + 1);

    act(() => useChatStore.setState({ inputMessage: 'hello' }));
    act(() => useChatStore.setState({ activeKnowledgeBaseIds: [], activeKnowledgeBaseNames: {} }));
    expect(chatView.mounts).toBe(mountsBeforeLoad + 1);
  });

  it('keeps the chat the store chose for home instead of replacing it with a new one', () => {
    // The incognito toggle starts a fresh chat and then navigates to `/`, which mounts this window with no id.
    // Replacing the id here would hand out a new one and drop the mode the toggle just set.
    useChatStore.setState({
      chatId: 'c-just-started',
      incognitoMode: true,
      messages: [],
      isMessagesLoaded: true,
      compactedSummary: null,
    });

    render(<ChatWindow />);

    expect(useChatStore.getState().chatId).toBe('c-just-started');
    expect(useChatStore.getState().incognitoMode).toBe(true);
  });

  it('still starts a new chat when home is reached from a conversation with messages', () => {
    useChatStore.setState({ chatId: 'c-previous', messages: [FIRST_MESSAGE], isMessagesLoaded: true });

    render(<ChatWindow />);

    expect(useChatStore.getState().chatId).not.toBe('c-previous');
  });
});
