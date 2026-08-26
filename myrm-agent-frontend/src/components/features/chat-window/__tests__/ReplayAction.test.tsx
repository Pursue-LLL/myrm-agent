import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import ReplayAction from '../ReplayAction';
import * as chatService from '@/services/chat';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}));

describe('ReplayAction Component', () => {
  it('renders verify replay button and triggers action', async () => {
    const replaySpy = vi.spyOn(chatService, 'replayChatSession').mockResolvedValue({
      session_id: 'chat-test-1',
      determinism_score: 1.0,
      tool_sequence_similarity: 1.0,
      tool_set_jaccard: 1.0,
      args_similarity: 1.0,
      original_tool_count: 2,
      replayed_tool_count: 2,
      drifted_tools: [],
      verdict: 'DETERMINISTIC',
    });

    render(<ReplayAction chatId="chat-test-1" />);
    const btn = screen.getByRole('button');
    expect(btn).toBeInTheDocument();

    fireEvent.click(btn);
    expect(replaySpy).toHaveBeenCalledWith('chat-test-1');
  });
});
