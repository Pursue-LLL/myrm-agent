// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';

import {
  appliesTimeout,
  buildCreatePayload,
  buildDeliveryPayload,
  buildSchedule,
  defaultTaskName,
  estimateMonthlyExecutions,
  hasContent,
  initialDraft,
  isSessionValid,
  isTimeoutInputValid,
  prerequisiteQuery,
  type CronCreateDraft,
  type UIJobMode,
} from '../cronCreateModel';

const draftOf = (changes: Partial<CronCreateDraft> = {}): CronCreateDraft => ({ ...initialDraft(), ...changes });
const DAILY = { kind: 'cron', expr: '0 9 * * *', tz: 'UTC' } as const;

describe('initialDraft', () => {
  it('starts on the template tab with an empty agent job bound to nothing', () => {
    expect(initialDraft()).toMatchObject({
      createMode: 'template',
      uiMode: 'agent',
      selectedBlueprint: null,
      createdJob: null,
      agentId: '__default__',
      workflowTemplateId: '__none__',
      scheduleKind: 'cron',
      sessionTarget: 'isolated',
      deliveryChannel: 'chat',
      acceptanceCriteria: [],
      overridePrerequisite: false,
    });
  });

  it('binds a dialog opened for one chat to that chat thread', () => {
    expect(initialDraft('chat-1').sessionTarget).toBe('main');
    expect(initialDraft(null).sessionTarget).toBe('isolated');
  });

  it('returns a fresh draft every time so a reset cannot share state with the last one', () => {
    expect(initialDraft().acceptanceCriteria).not.toBe(initialDraft().acceptanceCriteria);
  });
});

describe('buildSchedule', () => {
  const fields = { scheduleKind: 'cron' as const, cronExpr: '', intervalMinutes: '', onceAt: '' };

  it('describes a cron expression with the user time zone, trimmed', () => {
    expect(buildSchedule({ ...fields, cronExpr: '  0 9 * * *  ' }, 'UTC')).toEqual(DAILY);
  });

  it('has no schedule while the cron expression is blank', () => {
    expect(buildSchedule({ ...fields, cronExpr: '   ' }, 'UTC')).toBeNull();
  });

  it.each([
    ['5', 300_000],
    ['30', 1_800_000],
    [' 45 ', 2_700_000],
  ])('turns %s minutes into an interval of %i ms', (minutes, intervalMs) => {
    expect(buildSchedule({ ...fields, scheduleKind: 'interval', intervalMinutes: minutes }, 'Asia/Tokyo')).toEqual({
      kind: 'interval',
      interval_ms: intervalMs,
      tz: 'Asia/Tokyo',
    });
  });

  it.each(['', '0', '4', '-10', 'abc'])(
    'refuses the interval %j, below the scheduler minimum or not a number',
    (raw) => {
      expect(buildSchedule({ ...fields, scheduleKind: 'interval', intervalMinutes: raw }, 'UTC')).toBeNull();
    },
  );

  it('turns a one-off time into an ISO instant without a time zone', () => {
    const schedule = buildSchedule({ ...fields, scheduleKind: 'once', onceAt: '2030-01-01T09:00' }, 'UTC');
    expect(schedule).toEqual({ kind: 'once', run_at: new Date('2030-01-01T09:00').toISOString() });
  });

  it.each(['', '   ', 'not a date'])('refuses the one-off time %j', (raw) => {
    expect(buildSchedule({ ...fields, scheduleKind: 'once', onceAt: raw }, 'UTC')).toBeNull();
  });
});

describe('estimateMonthlyExecutions', () => {
  const fields = { scheduleKind: 'cron' as const, cronExpr: '', intervalMinutes: '' };

  it('counts a daily cron as about thirty runs a month', () => {
    const runs = estimateMonthlyExecutions({ ...fields, cronExpr: '0 9 * * *' });
    expect(runs).toBeGreaterThan(29);
    expect(runs).toBeLessThan(32);
  });

  it('counts every minute as far more than the interval of an hour', () => {
    const everyMinute = estimateMonthlyExecutions({ ...fields, cronExpr: '* * * * *' });
    const hourly = estimateMonthlyExecutions({ ...fields, scheduleKind: 'interval', intervalMinutes: '60' });
    expect(everyMinute).toBeGreaterThan(hourly ?? Infinity);
  });

  it('has no estimate for a blank cron, an invalid interval or an expression it cannot read', () => {
    expect(estimateMonthlyExecutions({ ...fields, cronExpr: ' ' })).toBeNull();
    expect(estimateMonthlyExecutions({ ...fields, scheduleKind: 'interval', intervalMinutes: '3' })).toBeNull();
    expect(estimateMonthlyExecutions({ ...fields, cronExpr: '0 9' })).toBeNull();
  });

  it('counts a one-off job as one run, even before a time is chosen', () => {
    expect(estimateMonthlyExecutions({ ...fields, scheduleKind: 'once' })).toBe(1);
  });
});

describe('what the user typed for each kind of job', () => {
  const typed = { prompt: 'the prompt', command: 'the command', scriptCode: 'the script' };

  it.each([
    ['agent', 'the prompt'],
    ['reminder', 'the prompt'],
    ['shell', 'the command'],
    ['script', 'the script'],
  ] as Array<[UIJobMode, string]>)('names a %s job after its own text', (uiMode, text) => {
    expect(defaultTaskName({ ...typed, uiMode, name: '' })).toBe(text);
  });

  it('prefers the name the user typed, trimmed', () => {
    expect(defaultTaskName({ ...typed, uiMode: 'agent', name: '  Morning brief ' })).toBe('Morning brief');
  });

  it('keeps only the first thirty characters of the text, and drops the surrounding blanks first', () => {
    const name = defaultTaskName({ ...typed, uiMode: 'reminder', name: '', prompt: `  ${'x'.repeat(40)}  ` });
    expect(name).toBe('x'.repeat(30));
  });

  it('is not valid until the active kind has text, ignoring text kept for the other kinds', () => {
    expect(hasContent({ ...typed, uiMode: 'agent', prompt: '   ' })).toBe(false);
    expect(hasContent({ ...typed, uiMode: 'shell', command: '' })).toBe(false);
    expect(hasContent({ ...typed, uiMode: 'script', scriptCode: ' ' })).toBe(false);
    expect(hasContent({ ...typed, uiMode: 'reminder' })).toBe(true);
  });

  it('asks the prerequisite check about the prompt for prompt kinds and about the command otherwise', () => {
    expect(prerequisiteQuery({ ...typed, uiMode: 'agent' })).toEqual({ prompt: 'the prompt', command: '' });
    expect(prerequisiteQuery({ ...typed, uiMode: 'reminder' })).toEqual({ prompt: 'the prompt', command: '' });
    expect(prerequisiteQuery({ ...typed, uiMode: 'shell' })).toEqual({ prompt: '', command: 'the command' });
    expect(prerequisiteQuery({ ...typed, uiMode: 'script' })).toEqual({ prompt: '', command: 'the script' });
  });
});

describe('run time limit and session validity', () => {
  it('has no limit to set for a reminder', () => {
    expect(appliesTimeout('reminder')).toBe(false);
    expect(appliesTimeout('agent')).toBe(true);
    expect(appliesTimeout('shell')).toBe(true);
    expect(appliesTimeout('script')).toBe(true);
  });

  it.each(['', '  ', '10', '3600', '900'])('accepts the limit %j', (raw) => {
    expect(isTimeoutInputValid('agent', raw)).toBe(true);
  });

  it.each(['9', '3601', '1.5', '-30', 'abc'])('rejects the limit %j for a job that runs the agent', (raw) => {
    expect(isTimeoutInputValid('agent', raw)).toBe(false);
  });

  it('never rejects what was typed for a reminder', () => {
    expect(isTimeoutInputValid('reminder', '5')).toBe(true);
  });

  it('needs a chat only for a job bound to a thread', () => {
    expect(isSessionValid('isolated', null)).toBe(true);
    expect(isSessionValid('main', null)).toBe(false);
    expect(isSessionValid('main', 'chat-1')).toBe(true);
  });
});

describe('buildDeliveryPayload', () => {
  it('sends nothing for the default chat delivery, whatever recipient was typed', () => {
    expect(buildDeliveryPayload('chat', 'ignored')).toBeUndefined();
  });

  it('sends the channel with its trimmed recipient', () => {
    expect(buildDeliveryPayload('telegram', '  42 ')).toEqual({ channel: 'telegram', target: '42' });
  });

  it('leaves the recipient out when it is blank', () => {
    expect(buildDeliveryPayload('slack', '   ')).toEqual({ channel: 'slack' });
  });

  it('maps the silent choice to the name the API uses', () => {
    expect(buildDeliveryPayload('none', '')).toEqual({ channel: 'silent' });
  });
});

describe('buildCreatePayload', () => {
  const build = (
    changes: Partial<CronCreateDraft>,
    chatId: string | null = null,
    workflowArgs: Record<string, string> | null = null,
  ) => buildCreatePayload({ draft: draftOf(changes), schedule: DAILY, chatId, workflowArgs });

  it('builds an agent job from its trimmed prompt and the chosen schedule', () => {
    expect(build({ prompt: '  Summarise  ' })).toEqual({
      name: 'Summarise',
      job_type: 'agent',
      schedule: DAILY,
      session_target: 'isolated',
      prompt: 'Summarise',
    });
  });

  it('names a reminder after its text when no name is typed, because the server refuses a blank name', () => {
    const payload = build({ uiMode: 'reminder', prompt: 'Stand up' });
    expect(payload).toMatchObject({ name: 'Stand up', job_type: 'reminder', prompt: 'Stand up' });
  });

  it('builds a shell job from its command', () => {
    const payload = build({ uiMode: 'shell', command: ' ls -la ' });
    expect(payload).toMatchObject({ name: 'ls -la', job_type: 'shell', command: 'ls -la' });
    expect(payload).not.toHaveProperty('prompt');
  });

  it('builds a script job as a router job whose script is the pre-condition script', () => {
    const payload = build({ uiMode: 'script', scriptCode: ' print(1) ' });
    expect(payload).toMatchObject({ name: 'print(1)', job_type: 'router', pre_condition_script: 'print(1)' });
    expect(payload).not.toHaveProperty('prompt');
  });

  it('binds an agent job to the chosen agent and leaves the default agent out', () => {
    expect(build({ prompt: 'x', agentId: 'agent-7' })).toHaveProperty('agent_id', 'agent-7');
    expect(build({ prompt: 'x' })).not.toHaveProperty('agent_id');
  });

  it('keeps agent and workflow choices out of the other kinds of job', () => {
    const payload = build({ uiMode: 'reminder', prompt: 'x', agentId: 'agent-7', workflowTemplateId: 't1' });
    expect(payload).not.toHaveProperty('agent_id');
    expect(payload).not.toHaveProperty('workflow_template_id');
  });

  it('sends the workflow template and its values, or the template alone when it has none', () => {
    const withArgs = build({ prompt: 'x', workflowTemplateId: 't1' }, null, { topic: 'ai' });
    expect(withArgs).toMatchObject({ workflow_template_id: 't1', workflow_template_args: { topic: 'ai' } });
    const withoutArgs = build({ prompt: 'x', workflowTemplateId: 't1' }, null, {});
    expect(withoutArgs).toHaveProperty('workflow_template_id', 't1');
    expect(withoutArgs).not.toHaveProperty('workflow_template_args');
  });

  it('sends the chat only for a job bound to a thread that has one', () => {
    expect(build({ prompt: 'x', sessionTarget: 'main' }, 'chat-1')).toMatchObject({
      session_target: 'main',
      chat_id: 'chat-1',
    });
    expect(build({ prompt: 'x', sessionTarget: 'isolated' }, 'chat-1')).not.toHaveProperty('chat_id');
    expect(build({ prompt: 'x', sessionTarget: 'main' }, null)).not.toHaveProperty('chat_id');
  });

  it('sends the delivery channel and recipient only when it is not the default chat', () => {
    expect(build({ prompt: 'x', deliveryChannel: 'telegram', deliveryTarget: '42' })).toHaveProperty('delivery', {
      channel: 'telegram',
      target: '42',
    });
    expect(build({ prompt: 'x', deliveryChannel: 'chat', deliveryTarget: '42' })).not.toHaveProperty('delivery');
  });

  it('sends the acceptance criteria that have a description, trimmed, and none when all are blank', () => {
    const criteria = [
      { type: 'semantic', description: '  covers the news  ' },
      { type: 'shell', description: '   ' },
      { type: 'shell', description: 'test -s out.txt' },
    ];
    expect(build({ prompt: 'x', acceptanceCriteria: criteria })).toHaveProperty('acceptance_criteria', [
      { type: 'semantic', description: 'covers the news' },
      { type: 'shell', description: 'test -s out.txt' },
    ]);
    const blank = build({ prompt: 'x', acceptanceCriteria: [{ type: 'semantic', description: ' ' }] });
    expect(blank).not.toHaveProperty('acceptance_criteria');
  });

  it('sends a valid run time limit and leaves out an empty one', () => {
    expect(build({ prompt: 'x', timeoutSeconds: '900' })).toHaveProperty('timeout_seconds', 900);
    expect(build({ prompt: 'x', timeoutSeconds: '' })).not.toHaveProperty('timeout_seconds');
  });

  it('drops a run time limit typed before the job became a reminder', () => {
    expect(build({ uiMode: 'reminder', prompt: 'x', timeoutSeconds: '900' })).not.toHaveProperty('timeout_seconds');
  });

  it('asks the server to skip the prerequisite gate only when the user overrode it', () => {
    expect(build({ prompt: 'x', overridePrerequisite: true })).toHaveProperty('override_prerequisite', true);
    expect(build({ prompt: 'x' })).not.toHaveProperty('override_prerequisite');
  });
});
