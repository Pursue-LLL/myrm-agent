/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import ChatWindow from '../ChatWindow';

const navigationMock = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  prefetch: vi.fn(),
  searchParams: new URLSearchParams(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: navigationMock.replace,
    push: navigationMock.push,
    prefetch: navigationMock.prefetch,
  }),
  useSearchParams: () => navigationMock.searchParams,
  usePathname: () => '/',
}));

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (key: string) => `${namespace || 'common'}.${key}`,
}));

vi.mock('../Chat', () => ({ default: () => <div data-testid="chat-view">Chat Stream</div> }));
vi.mock('../EmptyChat', () => ({ default: () => <textarea aria-label="message input" /> }));
vi.mock('../MessageListSkeleton', () => ({
  default: () => <div aria-label="Loading messages">skeleton</div>,
}));
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
vi.mock('@/components/features/cli-agent/PermissionDialog', () => ({ PermissionDialog: () => null }));
vi.mock('@/components/features/app-shell/VisualDesktopToggle', () => ({ VisualDesktopToggle: () => null }));
vi.mock('@/components/features/message-actions/SessionRevertButton', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/RunStatusChip', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/SessionAdvisorPanel', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryBadge', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryDialog', () => ({ default: () => null }));
vi.mock('@/components/features/settings/sections/system/ExecutionTraceTimeline', () => ({
  default: ({ sessionId }: { sessionId: string }) => (
    <div data-testid="execution-trace-view">Trace Timeline for {sessionId}</div>
  ),
}));

describe('ChatWindow Dual Tab [Chat | Trace]', () => {
  beforeEach(() => {
    vi.useRealTimers();
    navigationMock.searchParams = new URLSearchParams();
    useChatStore.setState({
      chatId: 'session-dual-tab-1',
      inputMessage: '',
      messages: [{ id: 'msg-1', role: 'user', content: 'hello' } as any],
      isMessagesLoaded: true,
      loading: false,
      messageAppeared: true,
      notFound: false,
      loadError: false,
    });
  });

  it('renders dual tab buttons and defaults to chat tab view', () => {
    render(<ChatWindow id="session-dual-tab-1" />);

    expect(screen.getByText('recovery.dualTabChat')).toBeInTheDocument();
    expect(screen.getByText('recovery.dualTabTrace')).toBeInTheDocument();

    expect(screen.getByTestId('chat-view')).toBeInTheDocument();
    expect(screen.queryByTestId('execution-trace-view')).not.toBeInTheDocument();
  });

  it('switches to trace tab view when trace tab button is clicked', () => {
    render(<ChatWindow id="session-dual-tab-1" />);

    const traceButton = screen.getByText('recovery.dualTabTrace').closest('button');
    expect(traceButton).not.toBeNull();

    act(() => {
      fireEvent.click(traceButton!);
    });

    expect(screen.getByTestId('execution-trace-view')).toBeInTheDocument();
    expect(screen.getByText('Trace Timeline for session-dual-tab-1')).toBeInTheDocument();
    expect(screen.queryByTestId('chat-view')).not.toBeInTheDocument();

    const chatButton = screen.getByText('recovery.dualTabChat').closest('button');
    expect(chatButton).not.toBeNull();

    act(() => {
      fireEvent.click(chatButton!);
    });

    expect(screen.getByTestId('chat-view')).toBeInTheDocument();
    expect(screen.queryByTestId('execution-trace-view')).not.toBeInTheDocument();
  });
});
