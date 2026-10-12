import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import HumanAttentionBar from '../HumanAttentionBar';
import useChatStore from '@/store/useChatStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

const stableT = (key: string, values?: { count?: number }) => {
  if (key === 'humanAttentionMultiple' && values?.count) {
    return `${values.count} pending`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/approval/useToolApprovalResolve', () => ({
  useToolApprovalResolve: () => ({ rejectAll: vi.fn(), isLoading: false }),
}));

describe('HumanAttentionBar', () => {
  beforeEach(() => {
    useChatStore.setState({
      chatId: 'chat-1',
      messages: [
        {
          messageId: 'msg-clarify',
          role: 'assistant',
          content: '',
          clarification: { answered: false, question: 'Which?' },
        },
      ],
    } as Partial<ReturnType<typeof useChatStore.getState>>);
    useToolApprovalStore.setState({ queue: [] });
    useDesktopControlApprovalStore.setState({
      pending: false,
      messageId: '',
      appName: '',
      reason: '',
    });
  });

  it('renders unified bar when clarify is pending', () => {
    render(<HumanAttentionBar messages={[{ messageId: 'msg-clarify' }]} onJumpToMessage={() => {}} />);
    expect(screen.getByTestId('human-attention-bar')).toBeInTheDocument();
    expect(screen.getByText('humanAttentionTitle')).toBeInTheDocument();
  });
});
