/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import ProgressSteps from '../ProgressSteps';
import type { ProgressItem } from '@/store/chat/types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: unknown) => unknown) => selector({ sendMessage: vi.fn(), messages: [] }),
}));

const REASON = 'The call was refused.';

const refusedStep = (error_category: string): ProgressItem => ({
  step_key: 'executing_code_error',
  tool_name: 'bash_code_execute_tool',
  status: 'error',
  error: REASON,
  error_category,
});

const expand = () => userEvent.click(screen.getByTestId('progress-steps-toggle'));

describe('ProgressSteps refusal tone', () => {
  it.each(['user_declined', 'approval_timeout'])(
    'shows %s in the warning tone, collapsed and expanded',
    async (category) => {
      render(<ProgressSteps messageId="msg-refused" steps={[refusedStep(category)]} loading={false} />);

      for (const badge of screen.getAllByText(`errorCategories.${category}`)) {
        expect(badge.className).toContain('text-amber-600');
        expect(badge.className).not.toContain('bg-destructive');
      }

      await expand();

      for (const badge of screen.getAllByText(`errorCategories.${category}`)) {
        expect(badge.className).toContain('text-amber-600');
        expect(badge.className).not.toContain('bg-destructive');
      }
      expect(screen.getByText(REASON).className).toContain('text-amber-700');
    },
  );

  it.each([
    ['user_declined', 'text-amber-700', 'text-destructive'],
    ['policy_denied', 'text-destructive', 'text-amber-700'],
  ])('draws the hint of a %s step in its own tone', async (category, shown, notShown) => {
    const HINT = 'Ask again when you are ready.';
    render(
      <ProgressSteps messageId="msg-hint" steps={[{ ...refusedStep(category), error_hint: HINT }]} loading={false} />,
    );
    await expand();

    const label = screen.getByText('diagnosticHint:');
    expect(label.className).toContain(shown);
    expect(label.className).not.toContain(notShown);
    expect(label.parentElement?.className).toContain(
      category === 'user_declined' ? 'border-amber' : 'border-destructive',
    );
    expect(screen.getByText(HINT)).toBeInTheDocument();
  });

  it('keeps a policy denial in the error tone, collapsed and expanded', async () => {
    render(<ProgressSteps messageId="msg-denied" steps={[refusedStep('policy_denied')]} loading={false} />);

    for (const badge of screen.getAllByText('errorCategories.policy_denied')) {
      expect(badge.className).toContain('bg-destructive');
      expect(badge.className).not.toContain('text-amber-600');
    }

    await expand();

    for (const badge of screen.getAllByText('errorCategories.policy_denied')) {
      expect(badge.className).toContain('bg-destructive');
    }
    expect(screen.getByText(REASON).className).toContain('text-destructive');
  });
});
