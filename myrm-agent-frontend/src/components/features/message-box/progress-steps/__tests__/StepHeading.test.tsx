import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StepStatusIcon, StepTitle } from '../StepHeading';
import type { StepVisualState } from '../stepTone';
import { AGENT_COLOR_CLASSES } from '../toolIcons';
import { BARE_DESTRUCTIVE_TEXT, makeStep, translate } from './progressStepsKit';

const NONE: StepVisualState = {
  isWarning: false,
  isBlocked: false,
  isError: false,
  isCurrent: false,
  isCompleted: false,
};

function iconOf(step = makeStep(), state = NONE): SVGElement {
  const { container } = render(<StepStatusIcon step={step} state={state} />);
  const icon = container.querySelector('svg');
  if (!icon) {
    throw new Error('the step icon did not render an svg');
  }
  return icon;
}

describe('StepStatusIcon', () => {
  it.each([
    ['an error', { ...NONE, isError: true }, 'text-destructive-text'],
    ['a warning', { ...NONE, isWarning: true }, 'text-amber-600'],
    ['a blocked step', { ...NONE, isBlocked: true }, 'text-amber-600'],
  ])('draws %s in its own tone', (_name, state, tone) => {
    const icon = iconOf(makeStep({ tool_name: 'bash_code_execute_tool' }), state);

    expect(icon).toHaveClass(tone);
    expect(icon).not.toHaveClass('text-foreground/70');
  });

  it('draws the icon of a system step in the primary tone and of a tool call in the foreground tone', () => {
    expect(iconOf(makeStep({ tool_name: undefined }))).toHaveClass('text-primary/70');
    expect(iconOf(makeStep({ tool_name: 'bash_code_execute_tool' }))).toHaveClass('text-foreground/70');
  });

  it('never draws an icon in the fill token', () => {
    const icon = iconOf(makeStep({ tool_name: 'bash_code_execute_tool' }), { ...NONE, isError: true });

    expect(icon.getAttribute('class')).not.toMatch(BARE_DESTRUCTIVE_TEXT);
  });
});

describe('StepTitle', () => {
  const renderTitle = (step = makeStep()) =>
    render(<StepTitle step={step} title="Reading the file" className="title-class" t={translate} />);

  it('is a heading that carries the caller class and the title', () => {
    renderTitle();

    const heading = screen.getByRole('heading', { level: 4 });
    expect(heading).toHaveTextContent('Reading the file');
    expect(heading).toHaveClass('title-class');
  });

  it('shows no badge on an ordinary step', () => {
    renderTitle();

    expect(screen.queryByText('smartFallbackBadge')).not.toBeInTheDocument();
    expect(screen.getByRole('heading').children).toHaveLength(0);
  });

  it('badges a step of an agent with its handle, preferring the display name', () => {
    const { unmount } = renderTitle(makeStep({ agent_instance: 'research_agent-a1b2' }));
    expect(screen.getByText('@Research-a1b2')).toBeInTheDocument();
    unmount();

    renderTitle(makeStep({ agent_instance: 'research_agent-a1b2', display_name: 'Scout' }));
    expect(screen.getByText('@Scout')).toBeInTheDocument();
    expect(screen.queryByText('@Research-a1b2')).not.toBeInTheDocument();
  });

  it('colours the agent badge by the theme colour the step carries', () => {
    // "a" hashes to green, so pink can only come from the theme colour.
    renderTitle(makeStep({ agent_instance: 'a', theme_color: 'pink' }));

    const badge = screen.getByText('@A');
    expect(badge).toHaveClass('text-pink-600');
    expect(badge).not.toHaveClass('text-green-600');
  });

  it.each([undefined, 'teal'])('colours the badge by the agent when the theme colour is %s', (themeColor) => {
    renderTitle(makeStep({ agent_instance: 'a', theme_color: themeColor }));

    const badge = screen.getByText('@A');
    expect(badge.className).toContain(AGENT_COLOR_CLASSES.green.badge);
  });

  it('badges the safe fallback step as a smart fallback', () => {
    renderTitle(makeStep({ step_key: 'safety_fallback_active' }));

    expect(screen.getByText('smartFallbackBadge')).toHaveClass('text-amber-600');
  });
});
