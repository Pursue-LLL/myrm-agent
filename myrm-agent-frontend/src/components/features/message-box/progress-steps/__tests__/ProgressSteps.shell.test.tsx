import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import ProgressSteps from '../ProgressSteps';
import { BARE_DESTRUCTIVE_TEXT, makeStep } from './progressStepsKit';

vi.mock('next-intl', async () => {
  const { translate } = await import('./progressStepsKit');
  return { useTranslations: () => translate, useLocale: () => 'en' };
});

const MESSAGE_ID = 'msg-shell';

const toggle = () => screen.getByTestId('progress-steps-toggle');
const panel = () => screen.getByTestId('progress-steps-panel');
const isExpanded = () => toggle().getAttribute('data-expanded') === 'true';

function renderSteps(steps: ProgressItem[], loading = false) {
  return render(<ProgressSteps messageId={MESSAGE_ID} steps={steps} loading={loading} />);
}

const titles = () => screen.queryAllByRole('heading', { level: 4 }).map((title) => title.textContent);

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ProgressSteps shell', () => {
  it('draws nothing without steps', () => {
    const { container } = renderSteps([]);

    expect(container).toBeEmptyDOMElement();
  });

  it('starts collapsed and opens and closes with its header', () => {
    renderSteps([makeStep()]);
    expect(isExpanded()).toBe(false);

    fireEvent.click(toggle());
    expect(isExpanded()).toBe(true);

    fireEvent.click(toggle());
    expect(isExpanded()).toBe(false);
  });

  it('opens with a click on the panel, which never closes it', () => {
    renderSteps([makeStep()]);

    fireEvent.click(panel());
    expect(isExpanded()).toBe(true);

    fireEvent.click(panel());
    expect(isExpanded()).toBe(true);
  });

  it('opens with a click on the collapsed summary inside the panel', () => {
    renderSteps([makeStep({ tool_name: 'file_read_tool' })]);

    fireEvent.click(screen.getByRole('heading', { level: 4 }));

    expect(isExpanded()).toBe(true);
  });

  it('declares the animations its child components use as global classes', () => {
    renderSteps([makeStep()]);

    const css = panel().querySelector('style')?.textContent ?? '';
    expect(css).toContain(':global(.slide-up)');
    expect(css).toContain(':global(.animate-rotate-step)');
    expect(css).toContain('@keyframes progressFlow');
  });
});

describe('ProgressSteps collapsed', () => {
  it('summarizes the newest step by its stage', () => {
    renderSteps([
      makeStep({ step_key: 'analyzing_query' }),
      makeStep({ step_key: 'read', tool_name: 'file_read_tool' }),
    ]);

    expect(titles()).toEqual(['categoryStageLabels.file']);
  });

  it('summarizes the latest image analysis instead of the newest step', () => {
    renderSteps([
      makeStep({ step_key: 'analyzing_image', progress_percent: 10 }),
      makeStep({ step_key: 'analyzing_image', tool_call_id: 'second', progress_percent: 90 }),
      makeStep({ step_key: 'read', tool_name: 'file_read_tool', progress_percent: 55 }),
    ]);

    expect(titles()).toEqual(['analyzing_image']);
    expect(screen.getByText('90%')).toBeInTheDocument();
    expect(screen.queryByText('10%')).not.toBeInTheDocument();
    expect(screen.queryByText('55%')).not.toBeInTheDocument();
  });

  it('shows the newest line of output while the turn is loading, and not afterwards', () => {
    const steps = [makeStep({ stdout: 'compiling\nlinking' })];
    const { rerender } = renderSteps(steps, true);
    expect(screen.getByText('linking')).toBeInTheDocument();

    rerender(<ProgressSteps messageId={MESSAGE_ID} steps={steps} loading={false} />);
    expect(screen.queryByText('linking')).not.toBeInTheDocument();
  });
});

describe('ProgressSteps expanded', () => {
  it('lists every step as a node of the tree', () => {
    renderSteps([makeStep({ step_key: 'alpha' }), makeStep({ step_key: 'beta' }), makeStep({ step_key: 'gamma' })]);

    fireEvent.click(toggle());

    expect(titles()).toEqual(['Alpha', 'Beta', 'Gamma']);
  });

  it('nests a step under the step it names as its parent', () => {
    renderSteps([makeStep({ step_key: 'alpha' }), makeStep({ step_key: 'beta', parent_step_key: 'alpha' })]);

    fireEvent.click(toggle());

    const beta = screen.getByRole('heading', { name: 'Beta' }).closest('.group') as HTMLElement;
    const alpha = screen.getByRole('heading', { name: 'Alpha' }).closest('.group') as HTMLElement;
    expect(alpha).toContainElement(beta);
  });

  it('draws the flowing light on the rail only while loading', () => {
    const { container, rerender } = renderSteps([makeStep()], true);
    fireEvent.click(toggle());
    expect(container.querySelector('[style*="progressFlow"]')).not.toBeNull();

    rerender(<ProgressSteps messageId={MESSAGE_ID} steps={[makeStep()]} loading={false} />);
    expect(container.querySelector('[style*="progressFlow"]')).toBeNull();
  });

  it('spins the dot of the newest step only while loading', () => {
    const steps = [makeStep({ step_key: 'alpha' }), makeStep({ step_key: 'beta', status: undefined })];
    const { container, rerender } = renderSteps(steps, true);
    fireEvent.click(toggle());
    const spinningSteps = new Set(
      Array.from(container.querySelectorAll('.animate-rotate-step')).map(
        (dot) => dot.closest('.group')?.querySelector('h4')?.textContent,
      ),
    );
    expect(Array.from(spinningSteps)).toEqual(['Beta']);

    rerender(<ProgressSteps messageId={MESSAGE_ID} steps={steps} loading={false} />);
    expect(container.querySelectorAll('.animate-rotate-step')).toHaveLength(0);
  });

  it('draws no text of any step in the fill token of destructive', () => {
    renderSteps([
      makeStep({
        status: 'error',
        error: 'The call was refused.',
        error_hint: 'Ask again later.',
        error_category: 'policy_denied',
        fault_side: 'tool',
        progress_percent: 40,
        notify_level: 'alert',
      }),
    ]);

    fireEvent.click(toggle());

    expect(panel().innerHTML).not.toMatch(BARE_DESTRUCTIVE_TEXT);
  });
});

describe('ProgressSteps folding', () => {
  const longTurn = () => Array.from({ length: 10 }, (_, index) => makeStep({ step_key: `step_${index}` }));

  it('folds the middle of a long turn, shows it on show more and folds it again on show less', () => {
    renderSteps(longTurn());
    fireEvent.click(toggle());
    expect(titles()).toEqual(['Step 0', 'Step 1', 'Step 7', 'Step 8', 'Step 9']);

    fireEvent.click(screen.getByRole('button', { name: /^folding\.showMore/ }));
    expect(titles()).toHaveLength(10);

    fireEvent.click(screen.getByRole('button', { name: 'folding.showLess' }));
    expect(titles()).toHaveLength(5);
  });
});

describe('ProgressSteps scrolling', () => {
  const scrollContainer = () => panel().querySelector(':scope > div') as HTMLElement;

  it('keeps the list scrolled to its end while loading and as steps arrive', () => {
    const scrollHeight = vi.spyOn(Element.prototype, 'scrollHeight', 'get').mockReturnValue(480);
    const { rerender } = renderSteps([makeStep({ step_key: 'alpha' })], true);
    fireEvent.click(toggle());
    expect(scrollContainer().scrollTop).toBe(480);

    scrollHeight.mockReturnValue(900);
    rerender(
      <ProgressSteps
        messageId={MESSAGE_ID}
        steps={[makeStep({ step_key: 'alpha' }), makeStep({ step_key: 'beta' })]}
        loading
      />,
    );
    expect(scrollContainer().scrollTop).toBe(900);
  });

  it('leaves the scroll position alone once the turn is done', () => {
    vi.spyOn(Element.prototype, 'scrollHeight', 'get').mockReturnValue(480);
    renderSteps([makeStep()], false);

    fireEvent.click(toggle());

    expect(scrollContainer().scrollTop).toBe(0);
  });
});

describe('ProgressSteps evicted output', () => {
  it.each(['evicted_file_ref', 'evicted_stderr_file_ref'] as const)('opens by itself for a step with %s', (field) => {
    renderSteps([makeStep({ [field]: 'output.txt' })]);

    expect(isExpanded()).toBe(true);
  });

  it('stays closed for a step without evicted output', () => {
    renderSteps([makeStep({ stdout: 'plain output' })]);

    expect(isExpanded()).toBe(false);
  });

  it('keeps the full output in reach when the user closes the list again', () => {
    renderSteps([makeStep({ evicted_file_ref: 'output.txt' })]);

    fireEvent.click(toggle());

    expect(isExpanded()).toBe(false);
    expect(screen.getByTestId('evicted-view-full-output')).toBeInTheDocument();
  });

  it('keeps the output of the newest step that has some in reach, whichever step the summary shows', () => {
    renderSteps([
      makeStep({ step_key: 'older', evicted_file_ref: 'old.txt', evicted_total_lines: 11 }),
      makeStep({ step_key: 'newer', evicted_file_ref: 'new.txt', evicted_total_lines: 22 }),
      makeStep({ step_key: 'latest' }),
    ]);

    fireEvent.click(toggle());

    expect(screen.getAllByTestId('evicted-view-full-output')).toHaveLength(1);
    expect(screen.getByText(/"lines":"22"/)).toBeInTheDocument();
    expect(screen.queryByText(/"lines":"11"/)).not.toBeInTheDocument();
  });
});

describe('ProgressSteps step detail', () => {
  it('opens the detail of a step from its info button and closes it with Escape', async () => {
    renderSteps([makeStep()]);
    fireEvent.click(toggle());

    fireEvent.click(screen.getByTitle('viewDetailTooltip'));
    const dialog = await screen.findByRole('dialog');

    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});
