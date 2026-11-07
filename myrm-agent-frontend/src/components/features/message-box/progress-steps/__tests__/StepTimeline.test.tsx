import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StepRail, StepStatusDot } from '../StepTimeline';
import type { StepVisualState } from '../stepTone';

const NONE: StepVisualState = {
  isWarning: false,
  isBlocked: false,
  isError: false,
  isCurrent: false,
  isCompleted: false,
};

function renderDot(state: StepVisualState, className?: string) {
  const { container } = render(<StepStatusDot state={state} className={className} />);
  const ring = container.firstElementChild as HTMLElement;
  return { ring, core: ring.firstElementChild as HTMLElement };
}

describe('StepStatusDot', () => {
  it.each([
    ['warning', { ...NONE, isWarning: true }, 'border-amber-500', 'bg-amber-500'],
    ['blocked', { ...NONE, isBlocked: true }, 'border-amber-600/70', 'bg-amber-600/80'],
    ['error', { ...NONE, isError: true }, 'border-destructive', 'bg-destructive'],
    ['in flight', { ...NONE, isCurrent: true }, 'border-primary', 'bg-primary'],
    ['completed', { ...NONE, isCompleted: true }, 'border-primary/70', 'bg-primary/70'],
    ['pending', NONE, 'border-muted-foreground/40', 'bg-muted-foreground/40'],
  ])('draws a %s step with its own ring and core', (_name, state, ringClass, coreClass) => {
    const { ring, core } = renderDot(state);

    expect(ring).toHaveClass(ringClass);
    expect(core).toHaveClass(coreClass);
  });

  it('spins only the dot of the step in flight', () => {
    const inFlight = renderDot({ ...NONE, isCurrent: true });
    expect(inFlight.ring).toHaveClass('animate-rotate-step');
    expect(inFlight.core).toHaveClass('animate-rotate-step');

    for (const state of [NONE, { ...NONE, isCompleted: true }, { ...NONE, isError: true }]) {
      const still = renderDot(state);
      expect(still.ring).not.toHaveClass('animate-rotate-step');
      expect(still.core).not.toHaveClass('animate-rotate-step');
    }
  });

  it.each([
    ['warning over error', { ...NONE, isWarning: true, isError: true }, 'border-amber-500'],
    ['blocked over error', { ...NONE, isBlocked: true, isError: true }, 'border-amber-600/70'],
    ['error over in flight', { ...NONE, isError: true, isCurrent: true }, 'border-destructive'],
    ['in flight over completed', { ...NONE, isCurrent: true, isCompleted: true }, 'border-primary'],
  ])('lets %s decide the ring', (_name, state, ringClass) => {
    expect(renderDot(state).ring).toHaveClass(ringClass);
  });

  it('keeps the fill tokens for the ring and core of an error, as they are not text', () => {
    const { ring, core } = renderDot({ ...NONE, isError: true });

    expect(ring.className).not.toContain('destructive-text');
    expect(core.className).not.toContain('destructive-text');
  });

  it('adds the caller class next to the base classes', () => {
    const { ring } = renderDot(NONE, 'z-10');

    expect(ring).toHaveClass('z-10', 'rounded-full', 'bg-background');
  });
});

describe('StepRail', () => {
  it('draws a vertical line inset from both ends and holds what it is given', () => {
    const { container, getByText } = render(
      <StepRail>
        <span>flow</span>
      </StepRail>,
    );

    const rail = container.firstElementChild as HTMLElement;
    expect([rail.style.top, rail.style.bottom]).toEqual(['0.5rem', '0.5rem']);
    expect(rail).toContainElement(getByText('flow'));
  });

  it('draws the bare line when it is given nothing', () => {
    const { container } = render(<StepRail />);

    expect(container.firstElementChild).toBeEmptyDOMElement();
  });
});
