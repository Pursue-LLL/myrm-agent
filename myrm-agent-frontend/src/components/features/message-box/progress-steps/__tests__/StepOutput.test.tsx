import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import { StepItemsView, StepTerminal } from '../StepOutput';
import { makeStep, searchItems } from './progressStepsKit';

vi.mock('../renderers', async () => (await import('./progressStepsStubs')).rendererModule);

// Source items also carry a url; kept out of a fresh literal so they type as url items, which is what they overlap with.
const sourceItems = [{ index: 1, type: 'web', url: 'https://example.com/a' }];

function renderItems(step: ProgressItem, isCurrent = false) {
  return render(<StepItemsView step={step} messageId="msg-1" index={3} isCurrent={isCurrent} />);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('StepItemsView', () => {
  it.each([
    ['no items', makeStep()],
    ['a plan', makeStep({ is_plan: true, items: [{ text: 'Plan the work' }] })],
    [
      'a delegated tool call, which is its own title',
      makeStep({ step_key: 'delegation_claude_tool', items: [{ text: 'claude: Read - note.txt' }] }),
    ],
  ])('draws nothing for %s', (_name, step) => {
    const { container } = renderItems(step);

    expect(container).toBeEmptyDOMElement();
  });

  it.each<[string, ProgressItem['items'], string]>([
    ['skill selections', [{ skill_name: 'research' }], 'SkillSelectRenderer'],
    ['file paths', [{ file_path: 'src/a.ts' }], 'FilePathRenderer'],
    ['a search tool call', searchItems('needle'), 'SearchToolCard'],
    ['code', [{ code: 'print(1)' }], 'CodeRenderer'],
    ['texts', [{ text: 'hello' }], 'TextItemsRenderer'],
    ['queries', [{ query: 'what is new' }], 'QueryItemsRenderer'],
    ['sources, which win over urls', sourceItems, 'SourcesRenderer'],
    ['urls', [{ url: 'https://example.com/a' }], 'URLItemsRenderer'],
  ])('draws %s with %s only, at the step position of the message', (_name, items, renderer) => {
    renderItems(makeStep({ items }));

    const drawn = screen.getAllByTestId(/.+/);
    expect(drawn).toHaveLength(1);
    expect(drawn[0]).toHaveAttribute('data-testid', renderer);
    expect(drawn[0]).toHaveAttribute('data-message-id', 'msg-1');
    expect(drawn[0]).toHaveAttribute('data-step-index', '3');
  });

  it('draws a plain text with the text renderer only', () => {
    renderItems(makeStep({ items: 'all done' }));

    const drawn = screen.getAllByTestId(/.+/);
    expect(drawn).toHaveLength(1);
    expect(drawn[0]).toHaveAttribute('data-testid', 'TextRenderer');
    expect(drawn[0]).toHaveAttribute('data-text', 'all done');
  });

  it('tells the search card which tool made the call', () => {
    renderItems(makeStep({ tool_name: 'grep_tool', items: searchItems('needle') }));

    expect(screen.getByTestId('SearchToolCard')).toHaveAttribute('data-tool-name', 'grep_tool');
  });

  it.each([true, false])('tells the sources and urls whether the step is in flight: %s', (isCurrent) => {
    const { unmount } = renderItems(makeStep({ items: sourceItems }), isCurrent);
    expect(screen.getByTestId('SourcesRenderer')).toHaveAttribute('data-current', String(isCurrent));
    unmount();

    renderItems(makeStep({ items: [{ url: 'https://example.com/a' }] }), isCurrent);
    expect(screen.getByTestId('URLItemsRenderer')).toHaveAttribute('data-current', String(isCurrent));
  });

  it('does not tell the other renderers about the step being in flight', () => {
    renderItems(makeStep({ items: [{ text: 'hello' }] }), true);

    expect(screen.getByTestId('TextItemsRenderer')).not.toHaveAttribute('data-current');
  });
});

describe('StepItemsView links', () => {
  it.each([
    ['TextItemsRenderer', [{ text: 'https://example.com/a' }]],
    ['URLItemsRenderer', [{ url: 'https://example.com/a' }]],
  ])('opens a link clicked in the %s in a new tab without an opener', (renderer, items) => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    renderItems(makeStep({ items }));

    fireEvent.click(screen.getByRole('button', { name: `open ${renderer}` }));

    expect(open).toHaveBeenCalledExactlyOnceWith('https://example.com/a', '_blank', 'noopener,noreferrer');
  });

  it.each(['plain words', 'www.example.com'])('opens nothing for the text %s, which is not a link', (text) => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    renderItems(makeStep({ items: [{ text }] }));

    fireEvent.click(screen.getByRole('button', { name: 'open TextItemsRenderer' }));

    expect(open).not.toHaveBeenCalled();
  });
});

describe('StepTerminal', () => {
  it('hands the terminal the output and every evicted file of the step', () => {
    render(
      <StepTerminal
        step={makeStep({
          stdout: 'line one',
          evicted_file_ref: 'out.txt',
          evicted_stored_chars: 100,
          evicted_total_lines: 7,
          evicted_storage_truncated: true,
          evicted_stderr_file_ref: 'err.txt',
          evicted_stderr_stored_chars: 50,
          evicted_stderr_total_lines: 3,
          evicted_stderr_storage_truncated: false,
        })}
      />,
    );

    expect(JSON.parse(screen.getByTestId('LiveTerminal').getAttribute('data-props') ?? '{}')).toEqual({
      stdout: 'line one',
      evictedFileRef: 'out.txt',
      evictedStoredChars: 100,
      evictedTotalLines: 7,
      evictedStorageTruncated: true,
      evictedStderrFileRef: 'err.txt',
      evictedStderrStoredChars: 50,
      evictedStderrTotalLines: 3,
      evictedStderrStorageTruncated: false,
    });
  });

  it('hands the terminal nothing for a step without output', () => {
    render(<StepTerminal step={makeStep()} />);

    expect(JSON.parse(screen.getByTestId('LiveTerminal').getAttribute('data-props') ?? '{}')).toEqual({});
  });
});
