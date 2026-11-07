// @vitest-environment jsdom
import { cleanup, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { CRON_PRESETS } from '../../cron-blueprints';
import {
  button,
  choose,
  click,
  combo,
  openCustom,
  openSelect,
  pickOption,
  placeholder,
  radio,
  resetKit,
  state,
  typeInto,
} from './createDialogTestKit';

beforeEach(resetKit);
afterEach(cleanup);

const previewIcon = () => document.querySelector('p svg.lucide-sparkles');
const onceInput = () => document.querySelector('input[type="datetime-local"]') as HTMLInputElement;

describe('schedule', () => {
  it('starts on a cron expression with one shortcut per preset', async () => {
    await openCustom();

    expect(placeholder('createCronPlaceholder')).toHaveValue('');
    for (const preset of CRON_PRESETS) {
      expect(button(preset.labelKey)).toBeInTheDocument();
    }
  });

  it('fills the expression from a preset', async () => {
    await openCustom();
    const preset = CRON_PRESETS[0];

    await click(button(preset.labelKey));

    expect(placeholder('createCronPlaceholder')).toHaveValue(preset.expr);
  });

  it('asks for whole minutes, at least five, for an interval', async () => {
    await openCustom();
    await choose(combo('createScheduleCron'), 'createScheduleInterval');

    expect(placeholder('30')).toHaveAttribute('min', '5');
    expect(screen.getByText('createIntervalUnit')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('createCronPlaceholder')).toBeNull();
  });

  it('asks for a date and time for a one-off job', async () => {
    await openCustom();
    await choose(combo('createScheduleCron'), 'createScheduleInterval');
    await choose(combo('createScheduleInterval'), 'createScheduleOnce');

    expect(onceInput()).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('30')).toBeNull();
  });

  it('shows what the schedule means only once it is valid', async () => {
    await openCustom();
    expect(previewIcon()).toBeNull();

    await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
    expect(previewIcon()).not.toBeNull();

    await typeInto(placeholder('createCronPlaceholder'), '  ');
    expect(previewIcon()).toBeNull();
  });

  it('rejects an interval below the scheduler minimum', async () => {
    await openCustom();
    await choose(combo('createScheduleCron'), 'createScheduleInterval');

    await typeInto(placeholder('30'), '3');
    expect(previewIcon()).toBeNull();

    await typeInto(placeholder('30'), '5');
    expect(previewIcon()).not.toBeNull();
  });

  it('keeps what was typed for each schedule kind while the user switches between them', async () => {
    await openCustom();
    await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
    await choose(combo('createScheduleCron'), 'createScheduleInterval');
    await typeInto(placeholder('30'), '15');
    await choose(combo('createScheduleInterval'), 'createScheduleCron');

    expect(placeholder('createCronPlaceholder')).toHaveValue('0 9 * * *');
    await choose(combo('createScheduleCron'), 'createScheduleInterval');
    expect(placeholder('30')).toHaveValue(15);
  });
});

describe('monthly estimate and deployment notice', () => {
  it('shows no estimate before the schedule is valid', async () => {
    await openCustom();

    expect(screen.queryByText('estMonthlyExecutions')).toBeNull();
  });

  it('estimates the monthly runs of a valid schedule without a warning', async () => {
    await openCustom();
    await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');

    expect(screen.getByText('estMonthlyExecutions')).toBeInTheDocument();
    expect(screen.queryByText('estHighFrequencyWarning')).toBeNull();
  });

  it('warns about a schedule that runs every minute', async () => {
    await openCustom();
    await typeInto(placeholder('createCronPlaceholder'), '* * * * *');

    expect(screen.getByText('estMonthlyExecutions')).toBeInTheDocument();
    expect(screen.getByText('estHighFrequencyWarning')).toBeInTheDocument();
  });

  it('shows no estimate for a schedule that practically never runs', async () => {
    await openCustom();
    await choose(combo('createScheduleCron'), 'createScheduleInterval');
    await typeInto(placeholder('30'), '10000000');

    expect(previewIcon()).toBeInTheDocument();
    expect(screen.queryByText('estMonthlyExecutions')).toBeNull();
  });

  it('counts a one-off job as one run', async () => {
    await openCustom();
    await choose(combo('createScheduleCron'), 'createScheduleOnce');

    expect(screen.getByText('estMonthlyExecutions')).toBeInTheDocument();
    expect(screen.queryByText('estHighFrequencyWarning')).toBeNull();
  });

  it('explains where a repeating job runs, but not a one-off one', async () => {
    await openCustom();
    expect(screen.getByTestId('deploy-notice')).toBeInTheDocument();

    await choose(combo('createScheduleCron'), 'createScheduleOnce');
    expect(screen.queryByTestId('deploy-notice')).toBeNull();
  });
});

describe('session mode', () => {
  it('offers its own session or a chat thread, described, for a repeating agent job', async () => {
    await openCustom();

    expect(screen.getByText('createSessionModeLabel')).toBeInTheDocument();
    expect(screen.getByText('createSessionIsolatedDesc')).toBeInTheDocument();

    await choose(combo('createSessionIsolated'), 'createSessionThread');
    expect(screen.getByText('createSessionThreadDesc')).toBeInTheDocument();
  });

  it.each(['jobTypeShell', 'jobTypeScript', 'jobTypeReminder'])('is not offered for a %s job', async (type) => {
    await openCustom();
    await click(radio(type));

    expect(screen.queryByText('createSessionModeLabel')).toBeNull();
  });

  it('is not offered for a one-off job', async () => {
    await openCustom();
    await choose(combo('createScheduleCron'), 'createScheduleOnce');

    expect(screen.queryByText('createSessionModeLabel')).toBeNull();
  });

  it('needs the user to pick a chat before a thread job can be created', async () => {
    state.chats = [
      { id: 'c1', title: 'Chat one' },
      { id: 'c2', title: 'Chat two' },
    ];
    await openCustom();
    await typeInto(placeholder('createPromptPlaceholder'), 'Summarise');
    await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
    expect(button('createSubmit')).toBeEnabled();

    await choose(combo('createSessionIsolated'), 'createSessionThread');
    expect(button('createSubmit')).toBeDisabled();

    await openSelect(combo('createSessionSelectChat'));
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(['Chat one', 'Chat two']);
    await pickOption('Chat two');
    expect(button('createSubmit')).toBeEnabled();
  });

  it('puts a thread job back in its own session when the schedule becomes a one-off', async () => {
    state.chats = [{ id: 'c1', title: 'Chat one' }];
    await openCustom();
    await typeInto(placeholder('createPromptPlaceholder'), 'Summarise');
    await choose(combo('createSessionIsolated'), 'createSessionThread');
    await choose(combo('createScheduleCron'), 'createScheduleOnce');
    await typeInto(onceInput(), '2030-01-01T09:00');

    expect(button('createSubmit')).toBeEnabled();
  });

  it('shows the chat a dialog was opened for instead of a chat select', async () => {
    await openCustom({ presetChatId: 'chat-9', presetChatTitle: 'Release planning' });

    expect(combo('createSessionThread')).toBeInTheDocument();
    expect(screen.getByText('Release planning')).toBeInTheDocument();
    expect(screen.queryByText('createSessionSelectChat')).toBeNull();
  });

  it('shows no chat name when the opened chat has no title', async () => {
    await openCustom({ presetChatId: 'chat-9', presetChatTitle: null });

    expect(combo('createSessionThread')).toBeInTheDocument();
    expect(screen.queryByText('createSessionSelectChat')).toBeNull();
  });
});

describe('default model note', () => {
  it('names the default model for an agent job on the default agent', async () => {
    state.providerPrimary = { providerId: 'openai', model: 'gpt-x' };
    await openCustom();

    expect(screen.getByText('estDefaultModel')).toBeInTheDocument();
  });

  it('is left out when no default model is configured', async () => {
    await openCustom();

    expect(screen.queryByText('estDefaultModel')).toBeNull();
  });

  it('is left out once another agent is chosen', async () => {
    state.providerPrimary = { providerId: 'openai', model: 'gpt-x' };
    state.agents = [{ id: 'a1', name: 'Alpha' }];
    await openCustom();

    await choose(combo('createAgentDefault'), 'Alpha');

    expect(screen.queryByText('estDefaultModel')).toBeNull();
  });

  it('is left out for the other kinds of job', async () => {
    state.providerPrimary = { providerId: 'openai', model: 'gpt-x' };
    await openCustom();
    await click(radio('jobTypeShell'));

    expect(screen.queryByText('estDefaultModel')).toBeNull();
  });
});

describe('run time limit', () => {
  it('is asked for every kind of job except a reminder', async () => {
    await openCustom();
    for (const type of ['jobTypeAgent', 'jobTypeShell', 'jobTypeScript']) {
      await click(radio(type));
      expect(screen.getByRole('spinbutton', { name: 'timeoutLabel' })).toBeInTheDocument();
    }

    await click(radio('jobTypeReminder'));
    expect(screen.queryByRole('spinbutton', { name: 'timeoutLabel' })).toBeNull();
  });
});

describe('acceptance criteria', () => {
  const addCriterion = () => screen.getByText('addCriterion').closest('button') as HTMLElement;
  const removeButtons = () => screen.getAllByRole('button').filter((item) => item.className.includes('h-7 w-7'));

  it('explains the feature while there are no criteria', async () => {
    await openCustom();

    expect(screen.getByText('acceptanceCriteriaHint')).toBeInTheDocument();

    await click(addCriterion());
    expect(screen.queryByText('acceptanceCriteriaHint')).toBeNull();
  });

  it('adds a semantic criterion whose description the user types', async () => {
    await openCustom();
    await click(addCriterion());

    expect(combo('criterionSemantic')).toBeInTheDocument();
    await typeInto(placeholder('criterionSemanticPlaceholder'), 'covers the news');
    expect(placeholder('criterionSemanticPlaceholder')).toHaveValue('covers the news');
  });

  it('switches the hint of a criterion to the shell wording when its type becomes shell', async () => {
    await openCustom();
    await click(addCriterion());
    await choose(combo('criterionSemantic'), 'criterionShell');

    expect(placeholder('criterionShellPlaceholder')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('criterionSemanticPlaceholder')).toBeNull();
  });

  it('removes only the criterion whose trash button was pressed', async () => {
    await openCustom();
    for (let count = 0; count < 3; count += 1) {
      await click(addCriterion());
    }
    const fields = screen.getAllByPlaceholderText('criterionSemanticPlaceholder');
    for (const [index, field] of fields.entries()) {
      await typeInto(field, ['first', 'second', 'third'][index] as string);
    }

    await click(removeButtons()[1] as HTMLElement);

    expect(
      screen.getAllByPlaceholderText('criterionSemanticPlaceholder').map((field) => (field as HTMLInputElement).value),
    ).toEqual(['first', 'third']);
  });

  it('stops offering more criteria at ten', async () => {
    await openCustom();
    for (let count = 0; count < 10; count += 1) {
      await click(addCriterion());
    }

    expect(screen.getAllByPlaceholderText('criterionSemanticPlaceholder')).toHaveLength(10);
    expect(screen.queryByText('addCriterion')).toBeNull();

    await click(removeButtons()[0] as HTMLElement);
    expect(screen.getByText('addCriterion')).toBeInTheDocument();
  });

  it('is only for agent jobs', async () => {
    await openCustom();
    await click(radio('jobTypeReminder'));

    const form = screen.getByTestId('cron-create-mode-custom').closest('[role="dialog"]') as HTMLElement;
    expect(within(form).queryByText('acceptanceCriteria')).toBeNull();
  });
});
