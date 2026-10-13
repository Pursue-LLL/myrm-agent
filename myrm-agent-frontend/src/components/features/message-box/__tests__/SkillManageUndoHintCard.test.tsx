import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { EXPAND_PROGRESS_STEPS_EVENT, type ExpandProgressStepsDetail } from '@/lib/chat/progressStepsUi';

import { SkillManageUndoHintCard } from '../SkillManageUndoHintCard';

// The global next-intl stub renders every translation key as itself.
const BODY = 'skillManageUndoHintBody';
const ACTION = 'skillManageUndoHintAction';

const cleanups: Array<() => void> = [];

function collectExpandEvents(): CustomEvent<ExpandProgressStepsDetail>[] {
  const received: CustomEvent<ExpandProgressStepsDetail>[] = [];
  const listener = (event: Event) => received.push(event as CustomEvent<ExpandProgressStepsDetail>);
  window.addEventListener(EXPAND_PROGRESS_STEPS_EVENT, listener);
  cleanups.push(() => window.removeEventListener(EXPAND_PROGRESS_STEPS_EVENT, listener));
  return received;
}

afterEach(() => {
  cleanups.splice(0).forEach((cleanup) => cleanup());
});

describe('SkillManageUndoHintCard', () => {
  it('explains where the undo lives and offers the action that opens it', () => {
    render(<SkillManageUndoHintCard messageId="m-1" />);

    expect(screen.getByText(BODY)).toBeDefined();
    expect(screen.getByRole('button', { name: ACTION })).toBeDefined();
  });

  it('asks the task steps of its own message to open', () => {
    const received = collectExpandEvents();
    render(<SkillManageUndoHintCard messageId="m-42" />);

    fireEvent.click(screen.getByRole('button', { name: ACTION }));

    expect(received).toHaveLength(1);
    expect(received[0].detail).toEqual({ messageId: 'm-42' });
  });

  it('does not broadcast an expand request without a message id', () => {
    const received = collectExpandEvents();
    render(<SkillManageUndoHintCard messageId="   " />);

    fireEvent.click(screen.getByRole('button', { name: ACTION }));

    expect(received).toHaveLength(0);
  });
});
