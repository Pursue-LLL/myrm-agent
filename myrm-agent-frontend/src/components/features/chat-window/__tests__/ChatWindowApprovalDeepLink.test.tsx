/** @vitest-environment jsdom */
import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useApprovalStore from '@/store/useApprovalStore';
import ChatWindow from '../ChatWindow';

const navigationMock = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  prefetch: vi.fn(),
  searchParams: new URLSearchParams(),
}));

const fetchPendingApprovalsMock = vi.hoisted(() => vi.fn());

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
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/hooks/usePendingApprovalsRecovery', () => ({
  usePendingApprovalsRecovery: () => undefined,
  fetchPendingApprovals: fetchPendingApprovalsMock,
}));

vi.mock('../Chat', () => ({ default: () => <div data-testid="chat" /> }));
vi.mock('../EmptyChat', () => ({ default: () => null }));
vi.mock('../MessageListSkeleton', () => ({ default: () => null }));
vi.mock('../ToolApprovalDialog', () => ({ default: () => null }));
vi.mock('../AgentInfoBanner', () => ({ default: () => null }));
vi.mock('../SubagentPromptButton', () => ({ default: () => null }));
vi.mock('../SubagentDashboard', () => ({ default: () => null }));
vi.mock('../goals/GoalStatusCard', () => ({ GoalStatusCard: () => null }));
vi.mock('../artifacts/ArtifactPortal', () => ({ default: () => null }));
vi.mock('@/components/features/cli-agent/PermissionDialog', () => ({ PermissionDialog: () => null }));
vi.mock('@/components/features/app-shell/VisualDesktopToggle', () => ({ VisualDesktopToggle: () => null }));
vi.mock('../LifeStatusCapsule', () => ({ LifeStatusCapsule: () => null }));

const originalSendMessage = useChatStore.getState().sendMessage;

describe('ChatWindow approval deep link', () => {
  beforeEach(() => {
    navigationMock.replace.mockClear();
    navigationMock.searchParams = new URLSearchParams('approval=ap-deep-link-1');
    fetchPendingApprovalsMock.mockReset();
    fetchPendingApprovalsMock.mockResolvedValue([
      {
        approval_id: 'ap-deep-link-1',
        user_id: 'local-user',
        action_type: 'delete_file',
        status: 'PENDING',
        severity: 'high',
        chat_id: 'session-1',
      },
    ]);
    useApprovalStore.setState({ isOpen: false, queue: [] });
    useChatStore.setState({
      chatId: 'session-1',
      messages: [],
      isMessagesLoaded: false,
      loading: false,
      messageAppeared: false,
      notFound: false,
      loadError: false,
      sendMessage: vi.fn(),
    });
  });

  afterEach(() => {
    useChatStore.setState({ sendMessage: originalSendMessage });
    useApprovalStore.setState({ isOpen: false, queue: [] });
  });

  it('opens the matching approval after chat loads and strips the query param', async () => {
    render(<ChatWindow id="session-1" />);
    expect(fetchPendingApprovalsMock).not.toHaveBeenCalled();

    act(() => {
      useChatStore.setState({ isMessagesLoaded: true });
    });

    await waitFor(() => {
      expect(fetchPendingApprovalsMock).toHaveBeenCalledTimes(1);
    });
    expect(useApprovalStore.getState().queue).toHaveLength(1);
    expect(useApprovalStore.getState().queue[0]?.approval_id).toBe('ap-deep-link-1');
    expect(navigationMock.replace).toHaveBeenCalledWith('/session-1', { scroll: false });
  });

  it('does not reapply the same approval query', async () => {
    useChatStore.setState({ isMessagesLoaded: true });
    const { rerender } = render(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(fetchPendingApprovalsMock).toHaveBeenCalledTimes(1);
    });

    rerender(<ChatWindow id="session-1" />);
    expect(fetchPendingApprovalsMock).toHaveBeenCalledTimes(1);
    expect(navigationMock.replace).toHaveBeenCalledTimes(1);
  });
});
