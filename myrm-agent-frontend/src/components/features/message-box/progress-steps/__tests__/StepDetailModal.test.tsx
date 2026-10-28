/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StepDetailModal } from '../StepDetailModal';
import type { ProgressItem } from '@/store/chat/types';

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (key: string) => `${namespace}.${key}`,
}));

const REASON = 'The call was refused.';

const refusedStep = (error_category: string): ProgressItem => ({
  step_key: 'executing_code_error',
  tool_name: 'bash_code_execute_tool',
  status: 'error',
  error: REASON,
  error_category,
});

const openModal = (step: ProgressItem) => render(<StepDetailModal step={step} open onOpenChange={vi.fn()} />);

describe('StepDetailModal outcome', () => {
  it.each(['user_declined', 'approval_timeout'])(
    'names a %s refusal by what happened, in the warning tone',
    (category) => {
      openModal(refusedStep(category));

      const badge = screen.getByText(`progressSteps.errorCategories.${category}`);
      expect(badge.className).toContain('text-amber-600');
      expect(badge.className).not.toContain('bg-destructive');
      expect(screen.getByText(REASON).className).toContain('text-amber-700');
      expect(screen.getByText(REASON).className).not.toContain('text-destructive');
    },
  );

  it('keeps a policy denial a failure, in the error tone', () => {
    openModal(refusedStep('policy_denied'));

    const badge = screen.getByText('progressSteps.statusLabels.error');
    expect(badge.className).toContain('bg-destructive');
    expect(screen.getByText(REASON).className).toContain('text-destructive');
    expect(screen.getByText(REASON).className).not.toContain('text-amber-700');
  });

  it('draws the hint of a refused call in the warning tone too', () => {
    openModal({ ...refusedStep('user_declined'), error_hint: 'Ask again when you are ready.' });

    expect(screen.getByText('Ask again when you are ready.').className).toContain('text-amber-700');
  });

  it('says a finished step succeeded in words of the interface language, not in the status code', () => {
    openModal({ step_key: 'tool_edit', tool_name: 'edit_file', status: 'success' });

    expect(screen.getByText('progressSteps.statusLabels.success')).toBeInTheDocument();
    expect(screen.queryByText('success')).toBeNull();
  });

  it('shows no outcome for a step that has no status yet', () => {
    openModal({ step_key: 'tool_edit', tool_name: 'edit_file' });

    expect(screen.queryByText('progressSteps.detailModal.status:')).toBeNull();
  });
});
