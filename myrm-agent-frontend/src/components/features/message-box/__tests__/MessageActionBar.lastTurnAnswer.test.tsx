'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MessageActionBar from '@/components/features/message-box/MessageActionBar';
import type { Message } from '@/store/chat/types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ setActiveSessionAnalyticsId: vi.fn(), setActiveSessionAnalyticsMessageId: vi.fn() }),
}));

vi.mock('@/components/features/message-actions/RegenerateMenu', () => ({
  default: () => (
    <button type="button" data-testid="regenerate">
      regenerate
    </button>
  ),
}));

vi.mock('@/components/features/message-actions/Copy', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/ExportMenu', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/MemoryFeedback', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/ReadAloud', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/RevertFiles', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/SaveEvalCase', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/SiblingNav', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/SaveToMemoryButton', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/ExtractToSkillButton', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/SaveToWikiButton', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/TokenUsageDisplay', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/ConsensusMetaDisplay', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/MemoryCitationsButton', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/TurnLoadedSkillsButton', () => ({ default: () => null }));
vi.mock('@/components/features/chat-window/ForkButton', () => ({ ForkButton: () => null }));

const assistantMessage: Message = {
  messageId: 'a1',
  chatId: 'chat-1',
  role: 'assistant',
  content: 'answer',
  createdAt: new Date('2026-10-13T00:00:00.000Z'),
};

function renderBar(props: { isLastTurnAnswer: boolean; isLast?: boolean; loading?: boolean }) {
  return render(
    <MessageActionBar
      message={assistantMessage}
      messageIndex={1}
      loading={props.loading ?? false}
      isLast={props.isLast ?? true}
      isLastTurnAnswer={props.isLastTurnAnswer}
      chatId="chat-1"
      enableEvalLab={false}
      markdownRef={{ current: null }}
      onCancel={vi.fn()}
      onRegenerate={vi.fn()}
    />,
  );
}

describe('MessageActionBar regenerate gating', () => {
  it('offers regenerate on the answer of the latest turn', () => {
    renderBar({ isLastTurnAnswer: true });

    expect(screen.getByTestId('regenerate')).toBeTruthy();
  });

  it('omits it on any other assistant message', () => {
    renderBar({ isLastTurnAnswer: false, isLast: false });

    expect(screen.queryByTestId('regenerate')).toBeNull();
  });

  it('omits it while the answer is still streaming', () => {
    renderBar({ isLastTurnAnswer: true, loading: true });

    expect(screen.queryByTestId('regenerate')).toBeNull();
  });
});
