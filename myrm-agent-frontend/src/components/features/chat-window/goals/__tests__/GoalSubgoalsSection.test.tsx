// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { GoalSubgoalsSection } from '../GoalSubgoalsSection';
import type { GoalState } from '../goalStatusTypes';

type Props = ComponentProps<typeof GoalSubgoalsSection>;

const t = ((key: string) => key) as unknown as Props['t'];

const goal = (status: GoalState['status'], subgoals: GoalState['subgoals'] = []): GoalState => ({
  goalId: 'g1',
  objective: 'Ship it',
  status,
  tokensUsed: 0,
  timeUsedSeconds: 0,
  subgoals,
});

function setup(overrides: Partial<Props> = {}) {
  const onAddSubgoal = vi.fn<Props['onAddSubgoal']>().mockResolvedValue(true);
  const onRemoveSubgoal = vi.fn<Props['onRemoveSubgoal']>();
  render(
    <GoalSubgoalsSection
      goal={goal('active')}
      isTerminal={false}
      onAddSubgoal={onAddSubgoal}
      onRemoveSubgoal={onRemoveSubgoal}
      t={t}
      {...overrides}
    />,
  );
  const input = screen.getByPlaceholderText('subgoalPlaceholder');
  return { input, onAddSubgoal, onRemoveSubgoal };
}

const type = (input: HTMLElement, value: string) => fireEvent.change(input, { target: { value } });

describe('GoalSubgoalsSection adding a sub-goal', () => {
  it('empties the box once the server took the sub-goal, from Enter and from the Add button', async () => {
    const { input, onAddSubgoal } = setup();

    type(input, 'write the docs');
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(input).toHaveValue(''));

    type(input, 'ship it');
    fireEvent.click(screen.getByRole('button', { name: 'addSubgoal' }));
    await waitFor(() => expect(input).toHaveValue(''));

    expect(onAddSubgoal.mock.calls.map(([text]) => text)).toEqual(['write the docs', 'ship it']);
  });

  it('keeps the text in the box when the server did not take it, from Enter and from the Add button', async () => {
    const { input, onAddSubgoal } = setup();
    onAddSubgoal.mockResolvedValue(false);

    type(input, 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0');
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(onAddSubgoal).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(input).toHaveValue('use key sk-AAAAAABBBBBBCCCCCCDDDD-0'));

    fireEvent.click(screen.getByRole('button', { name: 'addSubgoal' }));
    await waitFor(() => expect(onAddSubgoal).toHaveBeenCalledTimes(2));
    expect(input).toHaveValue('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');
  });

  it('adds a text once however often it is submitted while the request is out, then accepts the next one', async () => {
    const { input, onAddSubgoal } = setup();
    let answer: (taken: boolean) => void = () => {};
    onAddSubgoal.mockImplementationOnce(() => new Promise<boolean>((resolve) => (answer = resolve)));

    type(input, 'write the docs');
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'addSubgoal' }));
    expect(onAddSubgoal).toHaveBeenCalledTimes(1);

    answer(true);
    await waitFor(() => expect(input).toHaveValue(''));

    type(input, 'ship it');
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(onAddSubgoal).toHaveBeenCalledTimes(2));
  });

  it('keeps what was typed while the request was out, which is not the text that was taken', async () => {
    const { input, onAddSubgoal } = setup();
    let answer: (taken: boolean) => void = () => {};
    onAddSubgoal.mockImplementationOnce(() => new Promise<boolean>((resolve) => (answer = resolve)));

    type(input, 'write the docs');
    fireEvent.keyDown(input, { key: 'Enter' });
    type(input, 'write the docs and the changelog');
    answer(true);

    await waitFor(() => expect(onAddSubgoal).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    expect(input).toHaveValue('write the docs and the changelog');
  });

  it('sends nothing for a blank text and empties the box', () => {
    const { input, onAddSubgoal } = setup();

    type(input, '   ');
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onAddSubgoal).not.toHaveBeenCalled();
    expect(input).toHaveValue('');
  });
});

describe('GoalSubgoalsSection listing', () => {
  it('lists the sub-goals and removes one by position', () => {
    const { onRemoveSubgoal } = setup({ goal: goal('active', [{ text: 'first' }, { text: 'second' }]) });

    expect(screen.getByText('first')).toBeInTheDocument();
    const removeButtons = screen.getAllByRole('button', { name: 'Remove subgoal' });
    expect(removeButtons).toHaveLength(2);
    fireEvent.click(removeButtons[1] as HTMLElement);

    expect(onRemoveSubgoal).toHaveBeenCalledWith(1);
  });

  it('offers neither the input nor removal once the goal is over', () => {
    render(
      <GoalSubgoalsSection
        goal={goal('complete', [{ text: 'first' }])}
        isTerminal
        onAddSubgoal={vi.fn()}
        onRemoveSubgoal={vi.fn()}
        t={t}
      />,
    );

    expect(screen.getByText('first')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('subgoalPlaceholder')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Remove subgoal' })).toBeNull();
  });
});
