// @vitest-environment jsdom
import { cleanup, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { getBrowserTimezone } from '@/lib/utils/messageUtils';
import {
  choose,
  click,
  combo,
  fetchWorkflowTemplates,
  fillValidJob,
  listChannelStatuses,
  openCustom,
  placeholder,
  radio,
  resetKit,
  sentPayload,
  state,
  submit,
  templateOf,
  typeInto,
} from './createDialogTestKit';

beforeEach(resetKit);
afterEach(cleanup);

const dailyAtNine = { kind: 'cron', expr: '0 9 * * *', tz: getBrowserTimezone() };

/** Custom tab on the given kind of job, with its text and a daily schedule. */
async function fillJob(kind: string, textPlaceholder: string, text: string): Promise<void> {
  await openCustom();
  await click(radio(kind));
  await typeInto(placeholder(textPlaceholder), text);
  await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
}

describe('request for each kind of job', () => {
  it('sends an agent job named after its prompt, in its own session', async () => {
    await fillValidJob();
    await submit();

    expect(sentPayload()).toEqual({
      name: 'Summarise the news',
      job_type: 'agent',
      schedule: dailyAtNine,
      session_target: 'isolated',
      prompt: 'Summarise the news',
    });
  });

  it('prefers the name the user typed and trims every text', async () => {
    await fillValidJob();
    await typeInto(placeholder('createNamePlaceholder'), '  Morning brief ');
    await typeInto(placeholder('createPromptPlaceholder'), '  Summarise the news \n');
    await submit();

    expect(sentPayload()).toMatchObject({ name: 'Morning brief', prompt: 'Summarise the news' });
  });

  it('shortens a default name to the first 30 characters of the text', async () => {
    await fillValidJob();
    await typeInto(placeholder('createPromptPlaceholder'), 'x'.repeat(45));
    await submit();

    expect(sentPayload().name).toBe('x'.repeat(30));
  });

  it('sends a reminder named after its text', async () => {
    await fillJob('jobTypeReminder', 'createReminderPlaceholder', 'Stand up and stretch');
    await submit();

    expect(sentPayload()).toEqual({
      name: 'Stand up and stretch',
      job_type: 'reminder',
      schedule: dailyAtNine,
      session_target: 'isolated',
      prompt: 'Stand up and stretch',
    });
  });

  it('sends a shell job with its command', async () => {
    await fillJob('jobTypeShell', 'createCommandPlaceholder', ' ls -la ');
    await submit();

    expect(sentPayload()).toEqual({
      name: 'ls -la',
      job_type: 'shell',
      schedule: dailyAtNine,
      session_target: 'isolated',
      command: 'ls -la',
    });
  });

  it('sends a script job as a router job with its script', async () => {
    await fillJob('jobTypeScript', 'scriptPlaceholder', 'print(1)');
    await submit();

    expect(sentPayload()).toEqual({
      name: 'print(1)',
      job_type: 'router',
      schedule: dailyAtNine,
      session_target: 'isolated',
      pre_condition_script: 'print(1)',
    });
  });

  it('leaves the agent and the workflow template out of every other kind of job', async () => {
    state.agents = [{ id: 'a2', name: 'Beta' }];
    fetchWorkflowTemplates.mockResolvedValue({ templates: [templateOf('t1', 'Weekly report')] });
    await openCustom();
    await choose(combo('createAgentDefault'), 'Beta');
    await choose(combo('createWorkflowTemplateNone'), 'Weekly report');
    await click(radio('jobTypeShell'));
    await typeInto(placeholder('createCommandPlaceholder'), 'ls');
    await typeInto(placeholder('createCronPlaceholder'), '0 9 * * *');
    await submit();

    const payload = sentPayload();
    expect(payload).not.toHaveProperty('agent_id');
    expect(payload).not.toHaveProperty('workflow_template_id');
  });

  it('sends the agent that was chosen', async () => {
    state.agents = [{ id: 'a2', name: 'Beta' }];
    await fillValidJob();
    await choose(combo('createAgentDefault'), 'Beta');
    await submit();

    expect(sentPayload().agent_id).toBe('a2');
  });
});

describe('schedule in the request', () => {
  it('sends an interval in milliseconds', async () => {
    await openCustom();
    await typeInto(placeholder('createPromptPlaceholder'), 'Check');
    await choose(combo('createScheduleCron'), 'createScheduleInterval');
    await typeInto(placeholder('30'), '15');
    await submit();

    expect(sentPayload().schedule).toEqual({ kind: 'interval', interval_ms: 900_000, tz: getBrowserTimezone() });
  });

  it('sends a one-off run as an ISO instant', async () => {
    await openCustom();
    await typeInto(placeholder('createPromptPlaceholder'), 'Check');
    await choose(combo('createScheduleCron'), 'createScheduleOnce');
    await typeInto(document.querySelector('input[type="datetime-local"]') as HTMLInputElement, '2030-05-01T08:30');
    await submit();

    expect(sentPayload().schedule).toEqual({ kind: 'once', run_at: new Date('2030-05-01T08:30').toISOString() });
  });
});

describe('session in the request', () => {
  it('sends a thread job with the chat that was picked', async () => {
    state.chats = [{ id: 'c1', title: 'Chat one' }];
    await fillValidJob();
    await choose(combo('createSessionIsolated'), 'createSessionThread');
    await choose(combo('createSessionSelectChat'), 'Chat one');
    await submit();

    expect(sentPayload()).toMatchObject({ session_target: 'main', chat_id: 'c1' });
  });

  it('sends no chat once the job is back in its own session', async () => {
    state.chats = [{ id: 'c1', title: 'Chat one' }];
    await fillValidJob();
    await choose(combo('createSessionIsolated'), 'createSessionThread');
    await choose(combo('createSessionSelectChat'), 'Chat one');
    await choose(combo('createSessionThread'), 'createSessionIsolated');
    await submit();

    const payload = sentPayload();
    expect(payload.session_target).toBe('isolated');
    expect(payload).not.toHaveProperty('chat_id');
  });

  it('sends a job that was opened from a chat into that chat', async () => {
    await fillValidJob({ presetChatId: 'c9', presetChatTitle: 'Standup' });
    await submit();

    expect(sentPayload()).toMatchObject({ session_target: 'main', chat_id: 'c9' });
  });
});

describe('delivery in the request', () => {
  const telegramRunning = () => listChannelStatuses.mockResolvedValue([{ name: 'telegram', status: 'running' }]);

  it('sends no delivery while the results go to the chat', async () => {
    telegramRunning();
    await fillValidJob();
    await submit();

    expect(sentPayload()).not.toHaveProperty('delivery');
  });

  it('sends the channel with its trimmed recipient', async () => {
    telegramRunning();
    await fillValidJob();
    await click(radio('Telegram'));
    await typeInto(placeholder('123456789'), ' 42 ');
    await submit();

    expect(sentPayload().delivery).toEqual({ channel: 'telegram', target: '42' });
  });

  it('sends the channel alone when no recipient was typed', async () => {
    telegramRunning();
    await fillValidJob();
    await click(radio('Telegram'));
    await submit();

    expect(sentPayload().delivery).toEqual({ channel: 'telegram' });
  });
});

describe('acceptance criteria and run time limit in the request', () => {
  const addCriterion = () => click(screen.getByText('addCriterion').closest('button') as HTMLElement);

  it('sends the described criteria, trimmed, and leaves the blank ones out', async () => {
    await fillValidJob();
    await addCriterion();
    await choose(combo('criterionSemantic'), 'criterionShell');
    await typeInto(placeholder('criterionShellPlaceholder'), ' test -f out.txt ');
    await addCriterion();
    await typeInto(placeholder('criterionSemanticPlaceholder'), '  covers the news ');
    await addCriterion();
    await submit();

    expect(sentPayload().acceptance_criteria).toEqual([
      { type: 'shell', description: 'test -f out.txt' },
      { type: 'semantic', description: 'covers the news' },
    ]);
  });

  it('sends no criteria when none was described', async () => {
    await fillValidJob();
    await addCriterion();
    await submit();

    expect(sentPayload()).not.toHaveProperty('acceptance_criteria');
  });

  it('sends the run time limit that was typed', async () => {
    await fillValidJob();
    await typeInto(screen.getByRole('spinbutton', { name: 'timeoutLabel' }), '120');
    await submit();

    expect(sentPayload().timeout_seconds).toBe(120);
  });

  it('drops a run time limit when the job becomes a reminder', async () => {
    await fillValidJob();
    await typeInto(screen.getByRole('spinbutton', { name: 'timeoutLabel' }), '120');
    await click(radio('jobTypeReminder'));
    await typeInto(placeholder('createReminderPlaceholder'), 'Stretch');
    await submit();

    expect(sentPayload()).not.toHaveProperty('timeout_seconds');
  });
});
