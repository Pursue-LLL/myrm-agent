/** @vitest-environment jsdom */
import { act, render, waitFor } from '@testing-library/react';
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
  useTranslations: () => (key: string, values?: Record<string, string>) =>
    values?.restoreArg ? `${key}:${values.restoreArg}` : key,
}));

vi.mock('../Chat', () => ({ default: () => <div data-testid="chat" /> }));
vi.mock('../EmptyChat', () => ({ default: () => <textarea aria-label="message input" /> }));
vi.mock('../ToolApprovalDialog', () => ({ default: () => null }));
vi.mock('../AgentInfoBanner', () => ({ default: () => null }));
vi.mock('../SubagentPromptButton', () => ({ default: () => null }));
vi.mock('../SubagentDashboard', () => ({ default: () => null }));
vi.mock('../goals/GoalStatusCard', () => ({ GoalStatusCard: () => null }));
vi.mock('../artifacts/ArtifactPortal', () => ({ default: () => null }));
vi.mock('@/components/ui/cli-agent/PermissionDialog', () => ({ PermissionDialog: () => null }));
vi.mock('@/components/ui/VisualDesktopToggle', () => ({ VisualDesktopToggle: () => null }));
vi.mock('../LifeStatusCapsule', () => ({ LifeStatusCapsule: () => null }));

const originalSendMessage = useChatStore.getState().sendMessage;

describe('ChatWindow restore_arg prefill', () => {
  beforeEach(() => {
    vi.useRealTimers();
    const sendMessageMock = vi.fn<typeof originalSendMessage>();
    navigationMock.replace.mockClear();
    navigationMock.searchParams = new URLSearchParams('restore_arg=.context%2Fchat%2Fresult.txt%3A1-200');
    useChatStore.setState({
      chatId: 'session-1',
      inputMessage: '',
      pendingArchiveRestoreAction: null,
      pendingArchiveRestoreActions: [],
      messages: [],
      isMessagesLoaded: false,
      loading: false,
      messageAppeared: false,
      notFound: false,
      loadError: false,
      sendMessage: sendMessageMock,
    });
  });

  afterEach(() => {
    useChatStore.setState({ sendMessage: originalSendMessage });
  });

  it('waits for chat initialization before applying restore_arg', async () => {
    render(<ChatWindow id="session-1" />);

    expect(useChatStore.getState().inputMessage).toBe('');
    expect(navigationMock.replace).not.toHaveBeenCalled();

    act(() => {
      useChatStore.setState({ isMessagesLoaded: true });
    });

    await waitFor(() => {
      expect(useChatStore.getState().inputMessage).toBe(
        'contextHealth.pruning.restorePrompt:.context/chat/result.txt:1-200',
      );
    });
    expect(navigationMock.replace).toHaveBeenCalledWith('/session-1', { scroll: false });
    expect(useChatStore.getState().pendingArchiveRestoreAction).toEqual({
      type: 'archive_restore',
      restoreArg: '.context/chat/result.txt:1-200',
    });
    expect(useChatStore.getState().pendingArchiveRestoreActions).toEqual([
      {
        type: 'archive_restore',
        restoreArg: '.context/chat/result.txt:1-200',
      },
    ]);
  });

  it('does not auto-send or reapply the same restore_arg', async () => {
    useChatStore.setState({ isMessagesLoaded: true });
    const { rerender } = render(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(useChatStore.getState().inputMessage).toBe(
        'contextHealth.pruning.restorePrompt:.context/chat/result.txt:1-200',
      );
    });

    act(() => {
      useChatStore.setState({ inputMessage: 'manual edit' });
    });
    rerender(<ChatWindow id="session-1" />);

    expect(useChatStore.getState().inputMessage).toBe('manual edit');
    expect(useChatStore.getState().sendMessage).not.toHaveBeenCalled();
    expect(navigationMock.replace).toHaveBeenCalledTimes(1);
  });

  it('applies a new restore_arg once for the same session', async () => {
    useChatStore.setState({ isMessagesLoaded: true });
    const { rerender } = render(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(navigationMock.replace).toHaveBeenCalledTimes(1);
    });

    navigationMock.searchParams = new URLSearchParams('restore_arg=.context%2Fchat%2Fresult.txt%3A201-400');
    rerender(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(useChatStore.getState().inputMessage).toBe(
        'contextHealth.pruning.restorePrompt:.context/chat/result.txt:201-400',
      );
    });
    expect(useChatStore.getState().pendingArchiveRestoreAction).toEqual({
      type: 'archive_restore',
      restoreArg: '.context/chat/result.txt:201-400',
    });
    expect(useChatStore.getState().pendingArchiveRestoreActions).toEqual([
      {
        type: 'archive_restore',
        restoreArg: '.context/chat/result.txt:201-400',
      },
    ]);
    expect(navigationMock.replace).toHaveBeenCalledTimes(2);
  });
});
