import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import { StepErrorPanel } from '../StepErrorPanel';
import { BARE_DESTRUCTIVE_TEXT, makeStep, translate } from './progressStepsKit';

const ERROR = 'The upstream service refused the call.';
const failed = (overrides: Partial<ProgressItem> = {}): ProgressItem =>
  makeStep({ status: 'error', error: ERROR, ...overrides });

function renderPanel(step: ProgressItem, isWarning = false) {
  return render(<StepErrorPanel step={step} isWarning={isWarning} t={translate} />);
}

afterEach(() => {
  vi.restoreAllMocks();
  window.location.hash = '';
});

describe('StepErrorPanel visibility', () => {
  it.each([
    ['no error', undefined],
    ['a bare error flag', true],
    ['an empty message', ''],
  ])('draws nothing for %s', (_name, error) => {
    const { container } = renderPanel(makeStep({ status: 'error', error }));

    expect(container).toBeEmptyDOMElement();
  });
});

describe('StepErrorPanel tone', () => {
  it('draws an error in the destructive text token on a tinted box', () => {
    const { container } = renderPanel(failed({ error_hint: 'Try again later.' }));

    const box = container.firstElementChild as HTMLElement;
    expect(box).toHaveClass('bg-destructive/5', 'border-destructive/20');
    expect(screen.getByText(ERROR)).toHaveClass('text-destructive-text');
    expect(screen.getByText('diagnosticHint:')).toHaveClass('text-destructive-text');
    expect(box.innerHTML).not.toMatch(BARE_DESTRUCTIVE_TEXT);
  });

  it('draws a warning in amber, with nothing of the error colours', () => {
    const { container } = renderPanel(failed({ error_hint: 'Ask again when ready.' }), true);

    const box = container.firstElementChild as HTMLElement;
    expect(box).toHaveClass('bg-amber-50', 'border-amber-300');
    expect(screen.getByText(ERROR)).toHaveClass('text-amber-700');
    expect(screen.getByText('diagnosticHint:')).toHaveClass('text-amber-700');
    expect(box.innerHTML).not.toContain('destructive');
  });
});

describe('StepErrorPanel text', () => {
  it('turns a link in the message into an anchor that opens in a new tab', () => {
    renderPanel(failed({ error: 'Create a key at https://example.com/keys first.' }));

    const link = screen.getByRole('link', { name: 'https://example.com/keys' });
    expect(link).toHaveAttribute('href', 'https://example.com/keys');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('shows the diagnostic hint under its label, and no label without a hint', () => {
    const { unmount } = renderPanel(failed({ error_hint: 'Check the API key.' }));
    expect(screen.getByText('diagnosticHint:')).toBeInTheDocument();
    expect(screen.getByText('Check the API key.')).toBeInTheDocument();
    unmount();

    renderPanel(failed());
    expect(screen.queryByText('diagnosticHint:')).not.toBeInTheDocument();
  });
});

describe('StepErrorPanel recovery actions', () => {
  const actions = (...ids: string[]) =>
    ids.map((id) => ({ id, label: `label-${id}`, url: `https://example.com/${id}` }));

  it('lists the actions in order, and no row without actions that have a destination', () => {
    const { unmount } = renderPanel(failed({ recovery_actions: actions('first', 'second') }));
    expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual(['label-first', 'label-second']);
    unmount();

    renderPanel(failed({ recovery_actions: [{ id: 'none', label: 'label-none', url: '' }] }));
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it.each(['top_up', 'install_cli', 'mock_mode'])('gives the %s action the primary style', (id) => {
    renderPanel(failed({ recovery_actions: actions(id) }));

    expect(screen.getByRole('button')).toHaveClass('bg-primary');
  });

  it('gives any other action the plain style', () => {
    renderPanel(failed({ recovery_actions: actions('retry') }));

    const button = screen.getByRole('button');
    expect(button).toHaveClass('border-input');
    expect(button).not.toHaveClass('bg-primary');
  });

  it('opens an external destination in a new tab without an opener, and keeps the click to itself', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    const parentClick = vi.fn();
    render(
      <div role="presentation" onClick={parentClick}>
        <StepErrorPanel step={failed({ recovery_actions: actions('docs') })} isWarning={false} t={translate} />
      </div>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'label-docs' }));

    expect(open).toHaveBeenCalledExactlyOnceWith('https://example.com/docs', '_blank', 'noopener,noreferrer');
    expect(parentClick).not.toHaveBeenCalled();
  });

  it('opens a destination inside the app in the current page', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    renderPanel(failed({ recovery_actions: [{ id: 'billing', label: 'label-billing', url: '/#billing' }] }));

    fireEvent.click(screen.getByRole('button', { name: 'label-billing' }));

    expect(window.location.hash).toBe('#billing');
    expect(open).not.toHaveBeenCalled();
  });
});
