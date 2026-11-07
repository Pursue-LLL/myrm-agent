import { describe, expect, it } from 'vitest';
import type { Agent } from '@/services/agent';
import {
  agentSchema,
  buildAgentPayload,
  EMPTY_EXTRA_FIELDS,
  EMPTY_FORM_VALUES,
  extraFieldsFromAgent,
  formValuesFromAgent,
  type AgentExtraFields,
} from '../agentEditFormModel';

const BARE_AGENT: Agent = { id: 'a1', user_id: 'u1', name: 'Reviewer', created_at: '', updated_at: '' };

const FULL_AGENT: Agent = {
  ...BARE_AGENT,
  description: 'Reviews code',
  system_prompt: 'Be strict',
  avatar_url: 'icon:bot',
  agent_type: 'team',
  browser_source: 'extension',
  dialog_policy: 'auto_accept',
  session_recording: 'always',
  session_policy: { mode: 'idle', daily_reset_hour: 9, idle_minutes: 30 },
  command_bindings: [{ command_name: 'review', skill_ids: ['s1'] }],
  responsibility_scope: 'Owns reviews',
  owner_label: 'Alice',
  acceptance_criteria: ['a', 'b'],
};

const extra = (patch: Partial<AgentExtraFields> = {}): AgentExtraFields => ({ ...EMPTY_EXTRA_FIELDS, ...patch });

describe('agentSchema', () => {
  it('accepts a name alone', () => {
    expect(agentSchema.safeParse({ name: 'Bot' }).success).toBe(true);
  });

  it.each([
    ['empty name', { name: '' }, 'Name is required'],
    ['name over 50 characters', { name: 'x'.repeat(51) }, 'Name must be less than 50 characters'],
    [
      'description over 200 characters',
      { name: 'a', description: 'd'.repeat(201) },
      'Description must be less than 200 characters',
    ],
    [
      'system prompt over 10000 characters',
      { name: 'a', system_prompt: 'p'.repeat(10001) },
      'System prompt is too long',
    ],
  ])('rejects %s', (_, input, message) => {
    const result = agentSchema.safeParse(input);
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].message).toBe(message);
  });

  it('accepts the maximum lengths', () => {
    const input = { name: 'x'.repeat(50), description: 'd'.repeat(200), system_prompt: 'p'.repeat(10000) };
    expect(agentSchema.safeParse(input).success).toBe(true);
  });
});

describe('formValuesFromAgent / extraFieldsFromAgent', () => {
  it('fills blanks and defaults for a bare agent', () => {
    expect(formValuesFromAgent(BARE_AGENT)).toEqual({
      name: 'Reviewer',
      description: '',
      system_prompt: '',
      avatar_url: '',
    });
    expect(extraFieldsFromAgent(BARE_AGENT)).toEqual(EMPTY_EXTRA_FIELDS);
  });

  it('maps every stored field', () => {
    expect(formValuesFromAgent(FULL_AGENT)).toEqual({
      name: 'Reviewer',
      description: 'Reviews code',
      system_prompt: 'Be strict',
      avatar_url: 'icon:bot',
    });
    expect(extraFieldsFromAgent(FULL_AGENT)).toEqual({
      commandBindings: [{ command_name: 'review', skill_ids: ['s1'] }],
      agentType: 'team',
      sessionPolicyEnabled: true,
      sessionPolicy: { mode: 'idle', daily_reset_hour: 9, idle_minutes: 30 },
      browserSource: 'extension',
      dialogPolicy: 'auto_accept',
      sessionRecording: 'always',
      responsibilityScope: 'Owns reviews',
      ownerLabel: 'Alice',
      acceptanceCriteriaText: 'a\nb',
    });
  });

  it('treats null policy columns as defaults', () => {
    const fields = extraFieldsFromAgent({
      ...BARE_AGENT,
      browser_source: null,
      dialog_policy: null,
      session_recording: null,
      session_policy: null,
      command_bindings: null,
      acceptance_criteria: null,
    });
    expect(fields).toEqual(EMPTY_EXTRA_FIELDS);
  });
});

describe('buildAgentPayload', () => {
  const data = { ...EMPTY_FORM_VALUES, name: 'Bot' };

  it('submits default policies as null', () => {
    expect(buildAgentPayload(data, EMPTY_EXTRA_FIELDS)).toEqual({
      name: 'Bot',
      description: '',
      system_prompt: '',
      avatar_url: '',
      agent_type: 'individual',
      command_bindings: null,
      session_policy: null,
      browser_source: null,
      dialog_policy: null,
      session_recording: null,
      responsibility_scope: null,
      owner_label: null,
      acceptance_criteria: null,
    });
  });

  it('keeps non-default browser, dialog and recording choices', () => {
    const payload = buildAgentPayload(
      data,
      extra({ browserSource: 'remote', dialogPolicy: 'wait_for_agent', sessionRecording: 'on_failure' }),
    );
    expect(payload).toMatchObject({
      browser_source: 'remote',
      dialog_policy: 'wait_for_agent',
      session_recording: 'on_failure',
    });
  });

  it('submits the session policy only while it is enabled', () => {
    const sessionPolicy = { mode: 'idle' as const, daily_reset_hour: 4, idle_minutes: 15 };
    expect(buildAgentPayload(data, extra({ sessionPolicy })).session_policy).toBeNull();
    expect(buildAgentPayload(data, extra({ sessionPolicy, sessionPolicyEnabled: true })).session_policy).toEqual(
      sessionPolicy,
    );
  });

  it('trims responsibility fields and nulls blank ones', () => {
    expect(
      buildAgentPayload(data, extra({ responsibilityScope: '  Owns triage  ', ownerLabel: ' Bob ' })),
    ).toMatchObject({ responsibility_scope: 'Owns triage', owner_label: 'Bob' });
    expect(buildAgentPayload(data, extra({ responsibilityScope: '   ', ownerLabel: '\n' }))).toMatchObject({
      responsibility_scope: null,
      owner_label: null,
    });
  });

  it('drops command bindings without a name or skills', () => {
    const complete = { command_name: 'go', skill_ids: ['s1'] };
    const payload = buildAgentPayload(
      data,
      extra({
        commandBindings: [complete, { command_name: '', skill_ids: ['s2'] }, { command_name: 'x', skill_ids: [] }],
      }),
    );
    expect(payload.command_bindings).toEqual([complete]);
    expect(
      buildAgentPayload(data, extra({ commandBindings: [{ command_name: 'x', skill_ids: [] }] })).command_bindings,
    ).toBeNull();
  });

  it('trims acceptance criteria, skips blank lines and caps them at 20', () => {
    const text = [' first ', '', '   ', 'second', ...Array.from({ length: 30 }, (_, i) => `item${i}`)].join('\n');
    const criteria = buildAgentPayload(data, extra({ acceptanceCriteriaText: text })).acceptance_criteria;
    expect(criteria).toHaveLength(20);
    expect(criteria?.slice(0, 3)).toEqual(['first', 'second', 'item0']);
    expect(criteria?.[19]).toBe('item17');
    expect(buildAgentPayload(data, extra({ acceptanceCriteriaText: ' \n \n' })).acceptance_criteria).toBeNull();
  });

  it('round-trips a stored agent into the same server values', () => {
    const payload = buildAgentPayload(formValuesFromAgent(FULL_AGENT), extraFieldsFromAgent(FULL_AGENT));
    expect(payload).toEqual({
      name: 'Reviewer',
      description: 'Reviews code',
      system_prompt: 'Be strict',
      avatar_url: 'icon:bot',
      agent_type: 'team',
      command_bindings: FULL_AGENT.command_bindings,
      session_policy: FULL_AGENT.session_policy,
      browser_source: 'extension',
      dialog_policy: 'auto_accept',
      session_recording: 'always',
      responsibility_scope: 'Owns reviews',
      owner_label: 'Alice',
      acceptance_criteria: ['a', 'b'],
    });
  });
});
