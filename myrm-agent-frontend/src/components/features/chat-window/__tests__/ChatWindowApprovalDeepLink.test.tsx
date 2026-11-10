/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindow (POS: 聊天窗口，会话加载完成后打开 ?approval= 指向的待审批)
 * - ./chatWindowMocks (POS: 子组件替身与路由替身)
 *
 * [OUTPUT]
 * Vitest: 会话加载后才查待审批；打开链接指向的那一条（不是列表第一条）并清掉参数；同一参数不重复应用，
 * 地址清掉参数后同一链接再次使用会重新打开；审批已不在待处理或列表读取失败时只清参数。
 *
 * [POS]
 * fetchPendingApprovals 为替身，窗口、聊天 / 审批 store 为真实实现。
 */
import { StrictMode } from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation, openChatInStore } from './chatWindowMocks';
import { deferred } from '@/test-utils/deferred';
import useApprovalStore, { type ApprovalPayload } from '@/store/useApprovalStore';
import useChatStore from '@/store/useChatStore';
import ChatWindow from '../ChatWindow';

const fetchPendingApprovals = vi.hoisted(() => vi.fn<() => Promise<ApprovalPayload[]>>());

vi.mock('@/hooks/approval/usePendingApprovalsRecovery', () => ({
  usePendingApprovalsRecovery: () => undefined,
  fetchPendingApprovals,
}));

const LINKED = 'ap-deep-link-1';
const pending = (approvalId: string): ApprovalPayload => ({
  approval_id: approvalId,
  user_id: 'local-user',
  action_type: 'delete_file',
  status: 'PENDING',
  severity: 'high',
  chat_id: 'session-1',
});

describe('ChatWindow approval deep link', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.searchParams = new URLSearchParams({ approval: LINKED });
    fetchPendingApprovals.mockReset();
    fetchPendingApprovals.mockResolvedValue([pending(LINKED)]);
    useApprovalStore.setState({ isOpen: false, queue: [] });
    openChatInStore('session-1', { isMessagesLoaded: false });
  });

  it('opens the matching approval after chat loads and strips the query param', async () => {
    render(<ChatWindow id="session-1" />);
    expect(fetchPendingApprovals).not.toHaveBeenCalled();

    act(() => {
      useChatStore.setState({ isMessagesLoaded: true });
    });

    await waitFor(() => {
      expect(fetchPendingApprovals).toHaveBeenCalledTimes(1);
    });
    expect(useApprovalStore.getState().queue).toHaveLength(1);
    expect(useApprovalStore.getState().queue[0]?.approval_id).toBe(LINKED);
    expect(navigation.replace).toHaveBeenCalledWith('/session-1', { scroll: false });
  });

  it('opens the approval the link names, not whichever is first in the pending list', async () => {
    fetchPendingApprovals.mockResolvedValue([pending('ap-other'), pending(LINKED)]);
    useChatStore.setState({ isMessagesLoaded: true });
    render(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(useApprovalStore.getState().queue).toHaveLength(1);
    });
    expect(useApprovalStore.getState().queue[0]?.approval_id).toBe(LINKED);
  });

  it('does not reapply the same approval query', async () => {
    useChatStore.setState({ isMessagesLoaded: true });
    const { rerender } = render(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(fetchPendingApprovals).toHaveBeenCalledTimes(1);
    });

    rerender(<ChatWindow id="session-1" />);
    expect(fetchPendingApprovals).toHaveBeenCalledTimes(1);
    expect(navigation.replace).toHaveBeenCalledTimes(1);
  });

  it('cleans the address as soon as the link is followed, before the pending list arrives', async () => {
    const list = deferred<ApprovalPayload[]>();
    fetchPendingApprovals.mockReturnValue(list.promise);
    useChatStore.setState({ isMessagesLoaded: true });
    render(<ChatWindow id="session-1" />);

    expect(navigation.replace).toHaveBeenCalledExactlyOnceWith('/session-1', { scroll: false });
    expect(useApprovalStore.getState().queue).toHaveLength(0);

    await act(async () => list.resolve([pending(LINKED)]));
    expect(useApprovalStore.getState().queue).toHaveLength(1);
    expect(navigation.replace).toHaveBeenCalledOnce();
  });

  it('does not take the user back to the chat the link was followed in when the list arrives late', async () => {
    const list = deferred<ApprovalPayload[]>();
    fetchPendingApprovals.mockReturnValue(list.promise);
    useChatStore.setState({ isMessagesLoaded: true });
    const view = render(<ChatWindow id="session-1" />);

    navigation.searchParams = new URLSearchParams();
    act(() => openChatInStore('session-2'));
    view.rerender(<ChatWindow id="session-2" />);
    navigation.replace.mockClear();
    await act(async () => list.resolve([]));

    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it('looks nothing up on the new-chat page, where there is no conversation to open it in', () => {
    useChatStore.setState({ isMessagesLoaded: true });
    render(<ChatWindow />);

    expect(fetchPendingApprovals).not.toHaveBeenCalled();
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it('asks for the pending approvals once even when React replays the effects', async () => {
    useChatStore.setState({ isMessagesLoaded: true });
    render(
      <StrictMode>
        <ChatWindow id="session-1" />
      </StrictMode>,
    );

    await waitFor(() => expect(useApprovalStore.getState().queue).toHaveLength(1));
    expect(fetchPendingApprovals).toHaveBeenCalledOnce();
    expect(navigation.replace).toHaveBeenCalledOnce();
  });

  it('opens the approval again when the same link is used after the address was cleaned', async () => {
    useChatStore.setState({ isMessagesLoaded: true });
    const view = render(<ChatWindow id="session-1" />);
    await waitFor(() => expect(useApprovalStore.getState().queue).toHaveLength(1));

    // The router dropped the parameter and the user dealt with the card before following the link once more.
    navigation.searchParams = new URLSearchParams();
    view.rerender(<ChatWindow id="session-1" />);
    act(() => useApprovalStore.setState({ isOpen: false, queue: [] }));
    navigation.searchParams = new URLSearchParams({ approval: LINKED });
    view.rerender(<ChatWindow id="session-1" />);

    await waitFor(() => expect(useApprovalStore.getState().queue).toHaveLength(1));
    expect(fetchPendingApprovals).toHaveBeenCalledTimes(2);
  });

  it('opens nothing but still strips the query param when the approval is no longer pending', async () => {
    fetchPendingApprovals.mockResolvedValue([]);
    useChatStore.setState({ isMessagesLoaded: true });
    render(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(navigation.replace).toHaveBeenCalledWith('/session-1', { scroll: false });
    });
    expect(useApprovalStore.getState().queue).toHaveLength(0);
    expect(useApprovalStore.getState().isOpen).toBe(false);
  });

  it('logs and still strips the query param when the pending approvals cannot be loaded', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const failure = new Error('approvals service down');
    fetchPendingApprovals.mockRejectedValue(failure);
    useChatStore.setState({ isMessagesLoaded: true });
    render(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(navigation.replace).toHaveBeenCalledWith('/session-1', { scroll: false });
    });
    expect(warn).toHaveBeenCalledWith(expect.any(String), failure);
    expect(useApprovalStore.getState().queue).toHaveLength(0);
    warn.mockRestore();
  });
});
