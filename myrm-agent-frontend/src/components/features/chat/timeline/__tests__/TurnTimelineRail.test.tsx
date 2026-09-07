import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { TurnTimelineRail } from '../TurnTimelineRail';
import useChatStore from '@/store/useChatStore';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, opts?: { defaultMessage?: string }) => opts?.defaultMessage || key,
}));

describe('TurnTimelineRail', () => {
  beforeEach(() => {
    useChatStore.setState({
      turnOutlines: [
        {
          turn_index: 1,
          user_message_id: 'msg-u-1',
          assistant_message_id: 'msg-a-1',
          prompt_preview: 'Hello world first turn',
          reply_preview: 'Hi there! How can I help you today?',
          created_at: new Date().toISOString(),
          message_count: 2,
        },
        {
          turn_index: 2,
          user_message_id: 'msg-u-2',
          assistant_message_id: 'msg-a-2',
          prompt_preview: 'Second turn query',
          reply_preview: 'Here is the code implementation',
          created_at: new Date().toISOString(),
          message_count: 2,
        },
      ],
      messages: [
        {
          id: 'msg-u-2',
          role: 'user',
          content: 'Second turn query',
          createdAt: new Date(),
        } as any,
      ],
      activeTimelineTurnIndex: 2,
      loadThroughTurn: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('renders fixed-pitch turn rail when >= 2 turns exist', () => {
    render(<TurnTimelineRail />);
    const rail = screen.getByTestId('turn-timeline-rail');
    expect(rail).toBeInTheDocument();
  });

  it('shows hover preview outline when hovering over a turn indicator', () => {
    render(<TurnTimelineRail />);
    const dots = screen.getByTestId('turn-timeline-rail').children;
    expect(dots.length).toBe(2);

    fireEvent.mouseEnter(dots[0]);
    expect(screen.getByTestId('turn-preview-1')).toBeInTheDocument();
    expect(screen.getByText('Turn #1')).toBeInTheDocument();
    expect(screen.getByText('Hello world first turn')).toBeInTheDocument();

    fireEvent.mouseLeave(dots[0]);
    expect(screen.queryByTestId('turn-preview-1')).not.toBeInTheDocument();
  });

  it('triggers loadThroughTurn when clicking an unloaded turn', async () => {
    const loadThroughTurnMock = vi.fn().mockResolvedValue(undefined);
    useChatStore.setState({
      loadThroughTurn: loadThroughTurnMock,
    });

    render(<TurnTimelineRail />);
    const dots = screen.getByTestId('turn-timeline-rail').children;

    // Turn 1 is not in messages
    fireEvent.click(dots[0]);
    expect(loadThroughTurnMock).toHaveBeenCalledWith(1);
  });
});
