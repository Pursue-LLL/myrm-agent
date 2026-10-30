/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProgressSteps from '../ProgressSteps';
import type { ProgressItem, RecoveryAction } from '@/store/chat/types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const erroredStep = (recovery_actions: RecoveryAction[]): ProgressItem => ({
  step_key: 'llm_error',
  status: 'error',
  error: 'The provider could not process this request.',
  recovery_actions,
});

const renderExpanded = async (recovery_actions: RecoveryAction[]) => {
  render(<ProgressSteps messageId="msg-recovery" steps={[erroredStep(recovery_actions)]} loading={false} />);
  await userEvent.click(screen.getByTestId('progress-steps-toggle'));
};

describe('ProgressSteps recovery actions', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers only the actions that have a destination', async () => {
    await renderExpanded([
      { id: 'retry', label: 'Retry', url: '' },
      { id: 'check_network', label: 'Check Network', url: '' },
      { id: 'billing', label: 'Billing', url: 'https://example.com/billing' },
    ]);

    expect(screen.getByRole('button', { name: 'Billing' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Check Network' })).not.toBeInTheDocument();
  });

  it('renders no action row when no action has a destination', async () => {
    await renderExpanded([
      { id: 'wait', label: 'Wait', url: '' },
      { id: 'contact_support', label: 'Contact Support', url: '' },
    ]);

    expect(screen.getByText('The provider could not process this request.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Wait' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Contact Support' })).not.toBeInTheDocument();
  });

  it('opens an external destination in a new tab without an opener', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    await renderExpanded([{ id: 'billing', label: 'Billing', url: 'https://example.com/billing' }]);

    await userEvent.click(screen.getByRole('button', { name: 'Billing' }));

    expect(open).toHaveBeenCalledWith('https://example.com/billing', '_blank', 'noopener,noreferrer');
  });

  it('gives only the top-up action the primary style', async () => {
    await renderExpanded([
      { id: 'top_up', label: 'Top Up', url: '/pricing' },
      { id: 'switch_model', label: 'Switch Model', url: '/settings/models' },
    ]);

    expect(screen.getByRole('button', { name: 'Top Up' }).className).toContain('bg-primary');
    expect(screen.getByRole('button', { name: 'Switch Model' }).className).not.toContain('bg-primary');
  });
});
