import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StepTreeList } from '../StepTreeList';
import { makeContext, makeNode, makeStep } from './progressStepsKit';

vi.mock('../ProgressStepNode', async () => (await import('./progressStepsStubs')).nodesModule);

const roots = (count: number) =>
  Array.from({ length: count }, (_, index) => makeNode(makeStep({ step_key: `step_${index}` }), index));

function renderList(count: number, showAll = false, onShowAllChange = vi.fn()) {
  const parentClick = vi.fn();
  render(
    <div role="presentation" onClick={parentClick}>
      <StepTreeList
        roots={roots(count)}
        showAll={showAll}
        onShowAllChange={onShowAllChange}
        ctx={makeContext({ messageId: 'msg-4' })}
      />
    </div>,
  );
  return { onShowAllChange, parentClick };
}

const listedSteps = (list: HTMLElement) =>
  within(list)
    .getAllByRole('listitem')
    .map((item) => item.textContent);

describe('StepTreeList without folding', () => {
  it.each([1, 8])('draws the %i steps of a short turn in one list, with no folding entry', (count) => {
    renderList(count);

    const lists = screen.getAllByTestId('nodes');
    expect(lists).toHaveLength(1);
    expect(listedSteps(lists[0])).toEqual(Array.from({ length: count }, (_, index) => `step_${index}`));
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('draws no show less entry for a short turn, even when asked to show all', () => {
    renderList(5, true);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('hands the lists the context and the top level', () => {
    renderList(3);

    const [list] = screen.getAllByTestId('nodes');
    expect(list).toHaveAttribute('data-depth', '0');
    expect(list).toHaveAttribute('data-message-id', 'msg-4');
  });
});

describe('StepTreeList folded', () => {
  it('keeps the first two and the last three steps of a long turn and folds the middle', () => {
    renderList(9);

    const [head, tail] = screen.getAllByTestId('nodes');
    expect(screen.getAllByTestId('nodes')).toHaveLength(2);
    expect(listedSteps(head)).toEqual(['step_0', 'step_1']);
    expect(listedSteps(tail)).toEqual(['step_6', 'step_7', 'step_8']);
    for (const hidden of ['step_2', 'step_3', 'step_4', 'step_5']) {
      expect(screen.queryByText(hidden)).not.toBeInTheDocument();
    }
  });

  it('puts the show more entry between the head and the tail, with the count of folded steps', () => {
    renderList(9);

    const [head, tail] = screen.getAllByTestId('nodes');
    const showMore = screen.getByRole('button');
    expect(showMore).toHaveTextContent('folding.showMore:{"count":4}');
    expect(showMore).toHaveTextContent('folding.stepSummary:{"completed":4,"total":9}');
    expect(head.compareDocumentPosition(showMore) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(showMore.compareDocumentPosition(tail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('asks to show everything when show more is clicked, and keeps the click to itself', () => {
    const { onShowAllChange, parentClick } = renderList(9);

    fireEvent.click(screen.getByRole('button'));

    expect(onShowAllChange).toHaveBeenCalledExactlyOnceWith(true);
    expect(parentClick).not.toHaveBeenCalled();
  });
});

describe('StepTreeList showing all', () => {
  it('draws every step of a long turn in one list, followed by the show less entry', () => {
    renderList(9, true);

    const lists = screen.getAllByTestId('nodes');
    expect(lists).toHaveLength(1);
    expect(listedSteps(lists[0])).toHaveLength(9);
    expect(screen.getByRole('button')).toHaveTextContent('folding.showLess');
    expect(
      lists[0].compareDocumentPosition(screen.getByRole('button')) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('asks to fold again when show less is clicked, and keeps the click to itself', () => {
    const { onShowAllChange, parentClick } = renderList(9, true);

    fireEvent.click(screen.getByRole('button'));

    expect(onShowAllChange).toHaveBeenCalledExactlyOnceWith(false);
    expect(parentClick).not.toHaveBeenCalled();
  });
});
