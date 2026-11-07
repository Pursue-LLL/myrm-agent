import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import { CollapsedStepSummary } from '../CollapsedStepSummary';
import { BARE_DESTRUCTIVE_TEXT, makeStep, translate } from './progressStepsKit';

vi.mock('../StepOutput', async () => (await import('./progressStepsStubs')).outputModule);

interface RenderOptions {
  loading?: boolean;
  evictedStep?: ProgressItem | null;
}

function renderSummary(step: ProgressItem, { loading = false, evictedStep = null }: RenderOptions = {}) {
  return render(<CollapsedStepSummary step={step} evictedStep={evictedStep} loading={loading} t={translate} />);
}

const refusal = (category: string): Partial<ProgressItem> => ({
  status: 'error',
  error: 'refused',
  error_category: category,
});

describe('CollapsedStepSummary title', () => {
  it.each([
    ['a code run', { tool_name: 'bash_code_execute_tool' }, 'categoryStageLabels.execute'],
    ['a file read', { tool_name: 'file_read_tool' }, 'categoryStageLabels.file'],
    ['a thinking step', { step_key: 'analyzing_query' }, 'categoryStageLabels.thinking'],
    ['a step of no known kind', { step_key: 'something_else' }, 'categoryStageLabels.tool'],
    ['an image analysis', { step_key: 'analyzing_image' }, 'analyzing_image'],
  ])('names %s by its stage rather than by the call', (_name, overrides, label) => {
    renderSummary(makeStep(overrides));

    expect(screen.getByRole('heading', { level: 4 })).toHaveTextContent(new RegExp(`^${label}$`));
  });

  it('draws the title of a finished step in the foreground tone', () => {
    renderSummary(makeStep());

    expect(screen.getByRole('heading', { level: 4 })).toHaveClass('text-foreground');
  });
});

describe('CollapsedStepSummary tone', () => {
  it('draws an error in the destructive text token, from icon to title', () => {
    const { container } = renderSummary(makeStep({ ...refusal('policy_denied'), tool_name: 'file_read_tool' }));

    expect(screen.getByRole('heading', { level: 4 })).toHaveClass('text-destructive-text');
    expect(container.querySelector('svg')).toHaveClass('text-destructive-text');
    expect(container.innerHTML).not.toMatch(BARE_DESTRUCTIVE_TEXT);
  });

  it('draws a declined call in amber, with nothing of the error text colour', () => {
    const { container } = renderSummary(makeStep({ ...refusal('user_declined'), tool_name: 'file_read_tool' }));

    expect(screen.getByRole('heading', { level: 4 })).toHaveClass('text-amber-600');
    expect(container.querySelector('svg')).toHaveClass('text-amber-600');
    expect(container.innerHTML).not.toContain('text-destructive');
  });

  it('shows the localized error category', () => {
    renderSummary(makeStep(refusal('policy_denied')));

    expect(screen.getByText('errorCategories.policy_denied')).toBeInTheDocument();
  });

  it('shows no category badge on a step without one', () => {
    renderSummary(makeStep());

    expect(screen.queryByText(/^errorCategories\./)).not.toBeInTheDocument();
  });

  it.each([
    ['alert', 'text-destructive-text'],
    ['warn', 'text-amber-600'],
    ['info', 'text-muted-foreground/60'],
  ] as const)('draws the %s level of progress in %s', (level, tone) => {
    renderSummary(makeStep({ progress_percent: 64, notify_level: level }));

    expect(screen.getByText('64%')).toHaveClass(tone);
  });

  it('shows a progress of zero percent, and no percentage without progress', () => {
    const { unmount } = renderSummary(makeStep({ progress_percent: 0 }));
    expect(screen.getByText('0%')).toBeInTheDocument();
    unmount();

    renderSummary(makeStep());
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument();
  });

  it('lifts the dot above the row it sits in', () => {
    const { container } = renderSummary(makeStep());

    expect(container.querySelector('.rounded-full.bg-background')).toHaveClass('z-10');
  });

  it('spins the dot while the turn is loading and holds it still after', () => {
    const { container, rerender } = renderSummary(makeStep({ status: undefined }), { loading: true });
    expect(container.querySelectorAll('.animate-rotate-step').length).toBeGreaterThan(0);

    rerender(<CollapsedStepSummary step={makeStep()} evictedStep={null} loading={false} t={translate} />);
    expect(container.querySelectorAll('.animate-rotate-step')).toHaveLength(0);
  });
});

describe('CollapsedStepSummary latest output line', () => {
  it('shows the last non-empty line of the output while loading, trimmed', () => {
    const { container } = renderSummary(makeStep({ stdout: 'first line\n\n  last line  \n\n' }), { loading: true });

    expect(container.querySelector('p')?.textContent).toBe('last line');
    expect(screen.queryByText('first line')).not.toBeInTheDocument();
  });

  it('keeps the output line to itself once the turn is done', () => {
    renderSummary(makeStep({ stdout: 'last line' }), { loading: false });

    expect(screen.queryByText('last line')).not.toBeInTheDocument();
  });

  it.each([
    ['no output', undefined],
    ['an output of blank lines', '\n\n'],
    ['an output that ends in spaces only', 'text\n   '],
  ])('shows no line for %s', (_name, stdout) => {
    const { container } = renderSummary(makeStep({ stdout }), { loading: true });

    expect(container.querySelector('p')).toBeNull();
  });
});

describe('CollapsedStepSummary evicted output', () => {
  it('shows no terminal when no step has output evicted', () => {
    renderSummary(makeStep());

    expect(screen.queryByTestId('terminal')).not.toBeInTheDocument();
  });

  it('keeps the full output of the evicted step in reach, whichever step the summary shows', () => {
    renderSummary(makeStep({ step_key: 'latest' }), {
      evictedStep: makeStep({ step_key: 'older', evicted_file_ref: 'out.txt' }),
    });

    expect(screen.getByTestId('terminal')).toHaveAttribute('data-step-key', 'older');
  });
});

describe('CollapsedStepSummary animation', () => {
  it('leaves the entrance animation to the panel by marking its rows with the slide-up class', () => {
    const { container } = renderSummary(makeStep({ stdout: 'working' }), { loading: true });

    expect(container.querySelectorAll('.slide-up')).toHaveLength(2);
  });
});
