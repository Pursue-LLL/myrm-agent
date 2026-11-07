// @vitest-environment jsdom
import { act, cleanup, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { PrerequisiteCheckResponse } from '@/services/cron.types';
import {
  button,
  checkCronPrerequisite,
  choose,
  click,
  combo,
  createJob,
  elapse,
  fetchWorkflowTemplates,
  fillValidJob,
  openCustom,
  placeholder,
  prerequisiteOf,
  radio,
  resetKit,
  sentPayload,
  setDialogOpen,
  startFakeClock,
  state,
  stopFakeClock,
  submit,
  templateOf,
  toast,
  typeInto,
} from './createDialogTestKit';

beforeEach(resetKit);
afterEach(cleanup);

describe('workflow template placeholders', () => {
  const templates = [templateOf('t1', 'Weekly report', ['topic']), templateOf('t2', 'Plain template')];
  const topicField = () => screen.getByLabelText('topic');

  async function submitWithWeeklyReport(): Promise<void> {
    fetchWorkflowTemplates.mockResolvedValue({ templates });
    await fillValidJob();
    await choose(combo('createWorkflowTemplateNone'), 'Weekly report');
    await submit();
  }

  async function fillTopicAndConfirm(): Promise<void> {
    await typeInto(topicField(), ' AI chips ');
    await click(button('argsConfirmRun'));
  }

  it('asks for the values before creating a job from a template that has placeholders', async () => {
    await submitWithWeeklyReport();

    expect(createJob).not.toHaveBeenCalled();
    expect(button('argsConfirmRun')).toBeDisabled();

    await fillTopicAndConfirm();

    expect(sentPayload()).toMatchObject({
      workflow_template_id: 't1',
      workflow_template_args: { topic: 'AI chips' },
    });
  });

  it('creates at once from a template without placeholders', async () => {
    fetchWorkflowTemplates.mockResolvedValue({ templates });
    await fillValidJob();
    await choose(combo('createWorkflowTemplateNone'), 'Plain template');
    await submit();

    const payload = sentPayload();
    expect(payload.workflow_template_id).toBe('t2');
    expect(payload).not.toHaveProperty('workflow_template_args');
  });

  it('creates nothing when the user cancels the values', async () => {
    await submitWithWeeklyReport();
    await click(button('argsCancel'));

    expect(createJob).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('topic')).toBeNull();
    expect(placeholder('createPromptPlaceholder')).toHaveValue('Summarise the news');
  });

  it('reuses the confirmed values when the request is retried after a failure', async () => {
    createJob.mockRejectedValueOnce(new Error('boom'));
    await submitWithWeeklyReport();
    await fillTopicAndConfirm();
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('actionFail');

    await submit();

    expect(screen.queryByLabelText('topic')).toBeNull();
    expect(createJob).toHaveBeenCalledTimes(2);
    expect(createJob.mock.calls[1]?.[0]).toMatchObject({ workflow_template_args: { topic: 'AI chips' } });
  });

  it('does not ask for template values once the job is no longer an agent job', async () => {
    fetchWorkflowTemplates.mockResolvedValue({ templates });
    await openCustom();
    await choose(combo('createWorkflowTemplateNone'), 'Weekly report');
    await click(radio('jobTypeShell'));
    await typeInto(placeholder('createCommandPlaceholder'), 'ls');
    await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
    await submit();

    expect(screen.queryByLabelText('topic')).toBeNull();
    expect(sentPayload()).not.toHaveProperty('workflow_template_id');
  });

  it('asks again once the user has picked another template and come back', async () => {
    createJob.mockRejectedValueOnce(new Error('boom'));
    await submitWithWeeklyReport();
    await fillTopicAndConfirm();

    await choose(combo('Weekly report'), 'Plain template');
    await choose(combo('Plain template'), 'Weekly report');
    await submit();

    expect(createJob).toHaveBeenCalledTimes(1);
    expect(topicField()).toHaveValue('');
  });
});

describe('prerequisite check', () => {
  beforeEach(startFakeClock);
  afterEach(stopFakeClock);

  const promptField = () => placeholder('createPromptPlaceholder');
  const withAnswer = (answer: PrerequisiteCheckResponse) => checkCronPrerequisite.mockResolvedValue(answer);

  it('asks 400 ms after the text stops changing, not before', async () => {
    await openCustom();
    await typeInto(promptField(), 'Check');
    await elapse(399);
    expect(checkCronPrerequisite).not.toHaveBeenCalled();

    await typeInto(promptField(), 'Check it');
    await elapse(399);
    expect(checkCronPrerequisite).not.toHaveBeenCalled();

    await elapse(1);
    expect(checkCronPrerequisite).toHaveBeenCalledExactlyOnceWith({ prompt: 'Check it' });
  });

  it.each([
    ['jobTypeShell', 'createCommandPlaceholder'],
    ['jobTypeScript', 'scriptPlaceholder'],
  ])('asks about the command of a %s job instead of a prompt', async (kind, textPlaceholder) => {
    await openCustom();
    await click(radio(kind));
    await typeInto(placeholder(textPlaceholder), 'ls');
    await elapse(400);

    expect(checkCronPrerequisite).toHaveBeenCalledExactlyOnceWith({ command: 'ls' });
  });

  it('asks about the agent, workflow template and chat the job is bound to', async () => {
    state.agents = [{ id: 'a2', name: 'Beta' }];
    fetchWorkflowTemplates.mockResolvedValue({ templates: [templateOf('t2', 'Plain template')] });
    await openCustom({ presetChatId: 'c9' });
    await choose(combo('createAgentDefault'), 'Beta');
    await choose(combo('createWorkflowTemplateNone'), 'Plain template');
    await typeInto(promptField(), 'Check');
    await elapse(400);

    expect(checkCronPrerequisite).toHaveBeenCalledExactlyOnceWith({
      prompt: 'Check',
      agent_id: 'a2',
      workflow_template_id: 't2',
      chat_id: 'c9',
    });
  });

  it('does not ask again when a change leaves the text that would be sent as it was', async () => {
    await openCustom();
    await typeInto(promptField(), 'Check');
    await elapse(400);
    await click(radio('jobTypeReminder'));
    await elapse(400);

    expect(checkCronPrerequisite).toHaveBeenCalledTimes(1);
  });

  it('does not ask once the parent has closed the dialog', async () => {
    const opened = await openCustom();
    await typeInto(promptField(), 'Check');
    await setDialogOpen(opened, false);
    await elapse(400);

    expect(checkCronPrerequisite).not.toHaveBeenCalled();
  });

  it('shows that it is checking, then says the job has not been verified by hand yet', async () => {
    let answer: (response: PrerequisiteCheckResponse) => void = () => undefined;
    checkCronPrerequisite.mockImplementation(
      () =>
        new Promise<PrerequisiteCheckResponse>((resolve) => {
          answer = resolve;
        }),
    );
    await openCustom();
    await typeInto(promptField(), 'Check');
    expect(screen.queryByText('checkingPrerequisite')).toBeNull();

    await elapse(400);
    expect(screen.getByText('checkingPrerequisite')).toBeInTheDocument();

    await act(async () => answer(prerequisiteOf(false)));
    expect(screen.queryByText('checkingPrerequisite')).toBeNull();
    expect(screen.getByText('unmetTitle')).toBeInTheDocument();
  });

  it('offers no override once the job has been verified by hand', async () => {
    withAnswer(prerequisiteOf(true));
    await fillValidJob();
    await elapse(400);

    expect(screen.getByText('satisfiedTitle')).toBeInTheDocument();
    expect(screen.queryByLabelText('explicitOverrideLabel')).toBeNull();

    await submit();
    expect(sentPayload()).not.toHaveProperty('override_prerequisite');
  });

  it('sends the override the user ticked for an unverified job', async () => {
    withAnswer(prerequisiteOf(false));
    await fillValidJob();
    await elapse(400);
    await click(screen.getByLabelText('explicitOverrideLabel'));

    expect(screen.getByText('satisfiedTitle')).toBeInTheDocument();
    await submit();
    expect(sentPayload().override_prerequisite).toBe(true);
  });

  it('shows no card when the check fails', async () => {
    await openCustom();
    await typeInto(promptField(), 'Check');
    await elapse(400);

    expect(checkCronPrerequisite).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('checkingPrerequisite')).toBeNull();
    expect(screen.queryByText('unmetTitle')).toBeNull();
    expect(screen.queryByText('satisfiedTitle')).toBeNull();
  });

  it('drops the card when the text is emptied and asks again for the next text', async () => {
    withAnswer(prerequisiteOf(false));
    await openCustom();
    await typeInto(promptField(), 'Check');
    await elapse(400);
    expect(screen.getByText('unmetTitle')).toBeInTheDocument();

    await typeInto(promptField(), '');
    expect(screen.queryByText('unmetTitle')).toBeNull();
    await elapse(400);
    expect(checkCronPrerequisite).toHaveBeenCalledTimes(1);

    await typeInto(promptField(), 'Check again');
    await elapse(400);
    expect(checkCronPrerequisite).toHaveBeenCalledTimes(2);
    expect(screen.getByText('unmetTitle')).toBeInTheDocument();
  });

  it('forgets the answer and the override when the dialog starts over', async () => {
    withAnswer(prerequisiteOf(false));
    await openCustom();
    await typeInto(promptField(), 'Check');
    await elapse(400);
    await click(screen.getByLabelText('explicitOverrideLabel'));
    await click(button('cancel'));

    await click(screen.getByTestId('cron-create-mode-custom'));
    await typeInto(promptField(), 'Check');
    expect(screen.queryByText('unmetTitle')).toBeNull();
    expect(screen.queryByText('satisfiedTitle')).toBeNull();

    await elapse(400);
    expect(screen.getByText('unmetTitle')).toBeInTheDocument();
    expect(screen.getByLabelText('explicitOverrideLabel')).not.toBeChecked();
  });
});
