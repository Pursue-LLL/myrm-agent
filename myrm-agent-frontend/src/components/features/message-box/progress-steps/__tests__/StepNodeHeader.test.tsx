import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import { StepNodeHeader } from '../StepNodeHeader';
import { getStepVisualState } from '../stepTone';
import { BARE_DESTRUCTIVE_TEXT, makeStep, translate } from './progressStepsKit';

function renderHeader(step: ProgressItem, onViewDetail = vi.fn()) {
  const view = render(
    <StepNodeHeader
      step={step}
      state={getStepVisualState(step, false)}
      t={translate}
      tHumanize={translate}
      onViewDetail={onViewDetail}
    />,
  );
  return { ...view, onViewDetail };
}

const refusal = (category: string): Partial<ProgressItem> => ({
  status: 'error',
  error: 'refused',
  error_category: category,
});

describe('StepNodeHeader title', () => {
  it('names the step by its key made readable', () => {
    renderHeader(makeStep({ step_key: 'read_the_docs' }));

    expect(screen.getByRole('heading', { level: 4 })).toHaveTextContent('Read The Docs');
  });

  it('names a plan step by its own text and sets it in bold', () => {
    renderHeader(makeStep({ is_plan: true, items: [{ text: 'Research the topic' }] }));

    const title = screen.getByRole('heading', { level: 4 });
    expect(title).toHaveTextContent('Research the topic');
    expect(title).toHaveClass('font-semibold');
    expect(title).not.toHaveClass('font-normal');
  });

  it('sets a step that is not a plan in the regular weight', () => {
    renderHeader(makeStep());

    expect(screen.getByRole('heading', { level: 4 })).toHaveClass('font-normal');
  });

  it.each([
    ['an error', refusal('policy_denied'), 'text-destructive-text'],
    ['a declined call', refusal('user_declined'), 'text-amber-600'],
    ['a blocked step', { status: 'blocked' as const, error: 'waiting' }, 'text-amber-600'],
    ['a finished step', {}, 'text-foreground'],
  ])('draws the title of %s in %s', (_name, overrides, tone) => {
    renderHeader(makeStep(overrides));

    const title = screen.getByRole('heading', { level: 4 });
    expect(title).toHaveClass(tone);
    expect(title.className).not.toMatch(BARE_DESTRUCTIVE_TEXT);
  });
});

describe('StepNodeHeader badges', () => {
  it('shows the localized error category, and nothing without one', () => {
    const { unmount } = renderHeader(makeStep({ ...refusal('policy_denied') }));
    expect(screen.getByText('errorCategories.policy_denied')).toBeInTheDocument();
    unmount();

    renderHeader(makeStep());
    expect(screen.queryByText(/^errorCategories\./)).not.toBeInTheDocument();
  });

  it('shows the side at fault in the error tone of the destructive text token', () => {
    renderHeader(makeStep({ ...refusal('policy_denied'), fault_side: 'tool' }));

    const chip = screen.getByText('faultSides.tool');
    expect(chip).toHaveClass('bg-destructive/10', 'text-destructive-text', 'border-destructive/25');
  });

  it('shows the side at fault of a declined call in amber', () => {
    renderHeader(makeStep({ ...refusal('user_declined'), fault_side: 'user' }));

    const chip = screen.getByText('faultSides.user');
    expect(chip).toHaveClass('text-amber-700');
    expect(chip.className).not.toContain('destructive');
  });

  it.each([undefined, 'unknown'])('shows no side at fault when it is %s', (faultSide) => {
    renderHeader(makeStep({ ...refusal('policy_denied'), fault_side: faultSide }));

    expect(screen.queryByText(/^faultSides\./)).not.toBeInTheDocument();
  });
});

describe('StepNodeHeader duration', () => {
  it.each([
    [1, '1ms'],
    [450, '450ms'],
    [999, '999ms'],
    [1000, '1.0s'],
    [1500, '1.5s'],
    [12345, '12.3s'],
  ])('shows %i ms as %s', (durationMs, text) => {
    renderHeader(makeStep({ duration_ms: durationMs }));

    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it.each([undefined, 0, -5])('shows no duration for %s', (durationMs) => {
    const { container } = renderHeader(makeStep({ duration_ms: durationMs }));

    expect(container.querySelector('.font-mono')).toBeNull();
  });
});

describe('StepNodeHeader detail entry', () => {
  it('hands the step to the caller and keeps the click to itself', () => {
    const step = makeStep({ step_key: 'beta' });
    const parentClick = vi.fn();
    const onViewDetail = vi.fn();
    render(
      <div role="presentation" onClick={parentClick}>
        <StepNodeHeader
          step={step}
          state={getStepVisualState(step, false)}
          t={translate}
          tHumanize={translate}
          onViewDetail={onViewDetail}
        />
      </div>,
    );

    fireEvent.click(screen.getByTitle('viewDetailTooltip'));

    expect(onViewDetail).toHaveBeenCalledExactlyOnceWith(step);
    expect(parentClick).not.toHaveBeenCalled();
  });
});

describe('StepNodeHeader progress', () => {
  const trackAndFill = (container: HTMLElement) => {
    const fill = container.querySelector<HTMLElement>('[style*="width"]');
    if (!fill?.parentElement) {
      throw new Error('the progress bar did not render');
    }
    return { track: fill.parentElement, fill };
  };

  it('shows neither percentage nor bar without progress', () => {
    const { container } = renderHeader(makeStep());

    expect(screen.queryByText(/%$/)).not.toBeInTheDocument();
    expect(container.querySelector('[style*="width"]')).toBeNull();
  });

  it.each([
    [0, '0%'],
    [42, '42%'],
    [100, '100%'],
    [150, '100%'],
  ])('shows %i percent and fills %s of the bar', (percent, width) => {
    const { container } = renderHeader(makeStep({ progress_percent: percent }));

    expect(screen.getByText(`${percent}%`)).toBeInTheDocument();
    expect(trackAndFill(container).fill.style.width).toBe(width);
  });

  it.each([
    ['alert', 'text-destructive-text', 'bg-destructive/15', 'bg-destructive'],
    ['warn', 'text-amber-600', 'bg-amber-500/15', 'bg-amber-500'],
    ['info', 'text-muted-foreground/60', 'bg-muted/50', 'bg-primary/70'],
    [undefined, 'text-muted-foreground/60', 'bg-muted/50', 'bg-primary/70'],
  ] as const)('draws the %s level in %s, on a %s track filled with %s', (level, text, track, fill) => {
    const { container } = renderHeader(makeStep({ progress_percent: 30, notify_level: level }));

    const label = screen.getByText('30%');
    expect(label).toHaveClass(text);
    expect(label.className).not.toMatch(BARE_DESTRUCTIVE_TEXT);
    expect(trackAndFill(container).track).toHaveClass(track);
    expect(trackAndFill(container).fill).toHaveClass(fill);
  });
});
