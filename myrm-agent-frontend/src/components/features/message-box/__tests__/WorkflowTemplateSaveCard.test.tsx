import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import WorkflowTemplateSaveCard from '../WorkflowTemplateSaveCard';
import type { Message } from '@/store/chat/types/messages';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

describe('WorkflowTemplateSaveCard', () => {
  it('renders for completed dynamic workflow assistant messages', () => {
    const message: Message = {
      messageId: 'm1',
      chatId: 'chat-1',
      createdAt: new Date(),
      content: 'done',
      role: 'assistant',
      progressSteps: [{ step_key: 'workflow_init', status: 'success' }],
    };

    render(<WorkflowTemplateSaveCard message={message} chatId="chat-1" />);
    expect(screen.getByText('title')).toBeTruthy();
  });

  it('does not render for non-workflow messages', () => {
    const message: Message = {
      messageId: 'm2',
      chatId: 'chat-1',
      createdAt: new Date(),
      content: 'plain reply',
      role: 'assistant',
    };

    render(<WorkflowTemplateSaveCard message={message} chatId="chat-1" />);
    expect(screen.queryByText('title')).toBeNull();
  });
});
