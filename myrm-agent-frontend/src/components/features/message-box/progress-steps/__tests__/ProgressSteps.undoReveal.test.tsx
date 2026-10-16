/** @vitest-environment jsdom */
import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ProgressSteps from '../ProgressSteps';
import { expandProgressStepsForMessage } from '@/lib/chat/progressStepsUi';
import type { ProgressItem } from '@/store/chat/types';

// A stable translator reference: a fresh function per render re-triggers every effect keyed on `t`.
const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/store/useChatStore', () => {
  const state = { sendMessage: vi.fn(), messages: [] };
  const useChatStore = Object.assign((selector: (value: typeof state) => unknown) => selector(state), {
    getState: () => state,
  });
  return { default: useChatStore };
});

// The undo control has its own suite; here it only has to be on screen or not.
vi.mock('../SkillManageBatchRollbackAction', () => ({
  SkillManageBatchRollbackAction: ({ batchId }: { batchId: string }) => (
    <button type="button" aria-label="undo" data-testid="skill-manage-rollback-button" data-batch-id={batchId} />
  ),
}));

const MESSAGE_ID = 'msg-undo';

const skillSave = (overrides: Partial<ProgressItem> = {}): ProgressItem => ({
  step_key: 'tool_skill_manage_tool',
  tool_name: 'skill_manage_tool',
  status: 'success',
  skill_mutation_batch_id: 'batch-1',
  ...overrides,
});

/** `stepCount` steps without any undo control. A turn of more than eight top-level steps folds its middle. */
function plainTurn(stepCount: number): ProgressItem[] {
  return Array.from({ length: stepCount }, (_, index) => ({ step_key: `step_${index}`, status: 'success' }));
}

function turnWithSkillSave(stepCount: number, skillIndex: number): ProgressItem[] {
  const steps = plainTurn(stepCount);
  steps[skillIndex] = skillSave();
  return steps;
}

function renderTurn(steps: ProgressItem[]) {
  render(<ProgressSteps messageId={MESSAGE_ID} steps={steps} loading={false} />);
}

function askToOpenTaskSteps(messageId: string) {
  act(() => expandProgressStepsForMessage(messageId));
}

describe('ProgressSteps: the undo hint leads to the undo control', () => {
  it('unfolds a skill save that sits in the folded middle of a long turn', () => {
    renderTurn(turnWithSkillSave(11, 4));
    expect(screen.queryByTestId('skill-manage-rollback-button')).not.toBeInTheDocument();

    askToOpenTaskSteps(MESSAGE_ID);

    expect(screen.getByTestId('progress-steps-toggle')).toHaveAttribute('data-expanded', 'true');
    expect(screen.getByTestId('skill-manage-rollback-button')).toHaveAttribute('data-batch-id', 'batch-1');
    expect(screen.queryByText('folding.showMore')).not.toBeInTheDocument();
    expect(screen.getByText('folding.showLess')).toBeInTheDocument();
  });

  it('unfolds a skill save nested under a step in the folded middle', () => {
    const steps = plainTurn(11);
    steps[5] = skillSave({ parent_step_key: 'step_3' });
    renderTurn(steps);

    askToOpenTaskSteps(MESSAGE_ID);

    expect(screen.getByTestId('skill-manage-rollback-button')).toBeInTheDocument();
    expect(screen.queryByText('folding.showMore')).not.toBeInTheDocument();
  });

  it('keeps a long turn folded when the skill save is already among its last steps', () => {
    renderTurn(turnWithSkillSave(11, 9));

    askToOpenTaskSteps(MESSAGE_ID);

    expect(screen.getByTestId('skill-manage-rollback-button')).toBeInTheDocument();
    expect(screen.getByText('folding.showMore')).toBeInTheDocument();
    expect(screen.queryByText('folding.showLess')).not.toBeInTheDocument();
  });

  it('shows the undo control of a short turn without any folding involved', () => {
    renderTurn(turnWithSkillSave(6, 4));

    askToOpenTaskSteps(MESSAGE_ID);

    expect(screen.getByTestId('skill-manage-rollback-button')).toBeInTheDocument();
    expect(screen.queryByText('folding.showMore')).not.toBeInTheDocument();
    expect(screen.queryByText('folding.showLess')).not.toBeInTheDocument();
  });

  it('leaves a message alone when the hint of a different message asks to open its steps', () => {
    renderTurn(turnWithSkillSave(11, 4));

    askToOpenTaskSteps('another-message');

    expect(screen.getByTestId('progress-steps-toggle')).toHaveAttribute('data-expanded', 'false');
    expect(screen.queryByTestId('skill-manage-rollback-button')).not.toBeInTheDocument();
  });
});
