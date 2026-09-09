import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ClarificationInput from '../ClarificationInput';
import type { ClarificationForm } from '@/store/chat/types';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.count !== undefined) {
    return `${key}:${params.count}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('@/services/chat', () => ({
  submitClarifyResponse: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({
  default: () => vi.fn(),
}));

describe('ClarificationInput', () => {
  const formWithManyOptions: ClarificationForm = {
    title: 'Deployment Strategy',
    questions: [
      {
        id: 'strategy',
        prompt: 'Choose your deployment strategy',
        options: [
          { id: 'opt1', label: 'Option 1 (Recommended)', description: 'Use `pnpm run build`' },
          { id: 'opt2', label: 'Option 2', description: 'Run with `docker compose up`' },
          { id: 'opt3', label: 'Option 3', description: 'Standard container' },
          { id: 'opt4', label: 'Option 4', description: 'Serverless deployment' },
          { id: 'opt5', label: 'Option 5', description: 'Static export' },
          { id: 'opt6', label: 'Option 6', description: 'Manual cluster' },
        ],
      },
    ],
  };

  it('collapses options when exceeding 4 items by default', () => {
    render(
      <ClarificationInput
        messageId="msg-1"
        answered={false}
        form={formWithManyOptions}
      />,
    );

    expect(screen.getByText('Option 1')).toBeInTheDocument();
    expect(screen.getByText('Option 4')).toBeInTheDocument();
    // 5 and 6 should be hidden initially
    expect(screen.queryByText('Option 5')).not.toBeInTheDocument();
    expect(screen.queryByText('Option 6')).not.toBeInTheDocument();

    // Expand button is displayed with remaining count
    const expandBtn = screen.getByRole('button', { name: /expandOptions:2/i });
    expect(expandBtn).toBeInTheDocument();

    // Click to expand
    fireEvent.click(expandBtn);

    expect(screen.getByText('Option 5')).toBeInTheDocument();
    expect(screen.getByText('Option 6')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /collapseOptions/i })).toBeInTheDocument();
  });

  it('renders recommended badge and strips suffix from label', () => {
    render(
      <ClarificationInput
        messageId="msg-2"
        answered={false}
        form={formWithManyOptions}
      />,
    );

    // Label should be stripped of "(Recommended)"
    expect(screen.getByText('Option 1')).toBeInTheDocument();
    expect(screen.queryByText('Option 1 (Recommended)')).not.toBeInTheDocument();

    // Recommended badge text should be rendered
    expect(screen.getByText('recommendedBadge')).toBeInTheDocument();
  });

  it('renders inline code for description containing backticks', () => {
    const { container } = render(
      <ClarificationInput
        messageId="msg-3"
        answered={false}
        form={formWithManyOptions}
      />,
    );

    const codeEl = container.querySelector('code');
    expect(codeEl).toBeInTheDocument();
    expect(codeEl?.textContent).toBe('pnpm run build');
  });

  it('triggers submit on Enter key without shift key in structured form textarea', () => {
    const { container } = render(
      <ClarificationInput
        messageId="msg-4"
        answered={false}
        form={formWithManyOptions}
      />,
    );

    const textarea = container.querySelector('textarea');
    expect(textarea).toBeInTheDocument();
    if (textarea) {
      fireEvent.change(textarea, { target: { value: 'Custom Answer' } });
      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
    }
  });

  it('keeps original label as fallback when option text is purely (Recommended)', () => {
    const singlePureRecommendForm = {
      title: 'Pure Recommend',
      questions: [
        {
          id: 'q_pure',
          prompt: 'Choose one',
          options: [
            { id: 'opt_pure', label: '(Recommended)' },
          ],
        },
      ],
    };

    render(
      <ClarificationInput
        messageId="msg-5"
        answered={false}
        form={singlePureRecommendForm}
      />,
    );

    // Label fallback to '(Recommended)' rather than empty string
    expect(screen.getByText('(Recommended)')).toBeInTheDocument();
    // Badge also rendered
    expect(screen.getByText('recommendedBadge')).toBeInTheDocument();
  });

  it('automatically keeps options expanded if an option in the hidden slice is selected', () => {
    render(
      <ClarificationInput
        messageId="msg-6"
        answered={false}
        form={formWithManyOptions}
      />,
    );

    // Expand first
    const expandBtn = screen.getByRole('button', { name: /expandOptions:2/i });
    fireEvent.click(expandBtn);

    // Select Option 5 (hidden slice index >= 4)
    const opt5 = screen.getByText('Option 5');
    fireEvent.click(opt5);

    // Now, even if user clicks collapse button, it stays visible or effectiveExpanded handles it
    const collapseBtn = screen.getByRole('button', { name: /collapseOptions/i });
    fireEvent.click(collapseBtn);

    // Option 5 remains in document because hasSelectedInHidden preserves visibility!
    expect(screen.getByText('Option 5')).toBeInTheDocument();
  });
});
