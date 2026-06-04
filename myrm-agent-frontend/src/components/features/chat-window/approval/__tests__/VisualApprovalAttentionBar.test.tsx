import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import VisualApprovalAttentionBar from '@/components/features/chat-window/approval/VisualApprovalAttentionBar';
import type { ToolApprovalRequest } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    if (values) {
      return `${key}:${JSON.stringify(values)}`;
    }
    return key;
  },
}));

const rejectAllMock = vi.fn();

vi.mock('@/hooks/useToolApprovalResolve', () => ({
  useToolApprovalResolve: () => ({
    rejectAll: rejectAllMock,
    isLoading: false,
  }),
}));

const inlineRequest: ToolApprovalRequest = {
  requestId: 'req-inline-1',
  toolName: 'browser_click',
  toolInput: { ref: 'e12' },
  reason: 'Click submit',
  timeoutSeconds: 120,
  expiresAt: Math.floor(Date.now() / 1000) + 120,
  timeoutBehavior: 'deny',
  messageId: 'msg-42',
  displayMode: 'approval',
  chatId: 'chat-1',
  actionMode: 'agent',
};

describe('VisualApprovalAttentionBar', () => {
  beforeEach(() => {
    rejectAllMock.mockClear();
    useChatStore.setState({ chatId: 'chat-1' });
    useToolApprovalStore.setState({ queue: [], isResolving: false, batchDecisions: new Map() });
  });

  it('renders nothing when inline queue is empty', () => {
    const { container } = render(
      <VisualApprovalAttentionBar messages={[{ messageId: 'msg-42' }]} onJumpToMessage={() => {}} />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders attention bar for inline visual requests in active chat', () => {
    useToolApprovalStore.setState({ queue: [inlineRequest] });

    render(
      <VisualApprovalAttentionBar messages={[{ messageId: 'msg-42' }]} onJumpToMessage={() => {}} />,
    );

    expect(screen.getByTestId('visual-approval-attention-bar')).toBeInTheDocument();
    expect(screen.getByText('visualApprovalAttentionTitle')).toBeInTheDocument();
    expect(screen.getByText('browser_click')).toBeInTheDocument();
  });

  it('jumps to the message that owns the pending approval', () => {
    useToolApprovalStore.setState({ queue: [inlineRequest] });
    const onJumpToMessage = vi.fn();

    render(
      <VisualApprovalAttentionBar
        messages={[{ messageId: 'msg-1' }, { messageId: 'msg-42' }]}
        onJumpToMessage={onJumpToMessage}
      />,
    );

    fireEvent.click(screen.getByText('visualApprovalAttentionView'));
    expect(onJumpToMessage).toHaveBeenCalledWith(1);
  });

  it('calls rejectAll with inline requests from the active chat', () => {
    useToolApprovalStore.setState({ queue: [inlineRequest] });

    render(
      <VisualApprovalAttentionBar messages={[{ messageId: 'msg-42' }]} onJumpToMessage={() => {}} />,
    );

    fireEvent.click(screen.getByText('rejectAll'));
    expect(rejectAllMock).toHaveBeenCalledWith([inlineRequest]);
  });

  it('does not render for modal-only approvals', () => {
    useToolApprovalStore.setState({
      queue: [
        {
          ...inlineRequest,
          requestId: 'req-modal',
          toolName: 'bash',
        },
      ],
    });

    const { container } = render(
      <VisualApprovalAttentionBar messages={[{ messageId: 'msg-42' }]} onJumpToMessage={() => {}} />,
    );

    expect(container.firstChild).toBeNull();
  });
});
