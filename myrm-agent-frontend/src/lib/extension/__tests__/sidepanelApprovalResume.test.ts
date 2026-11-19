/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import {
  buildResumeValue,
  buildStreamBody,
  isResumeConflict,
} from '../../../../../myrm-agent-extension/src/sidepanel/approval.js';

describe('resume request', () => {
  it('approves with the one-decision shape the harness applies to every action', () => {
    expect(buildResumeValue(true)).toEqual({ decision: 'approve' });
  });

  it('rejects with the same denial reason the web app sends', () => {
    expect(buildResumeValue(false)).toEqual({ decision: 'reject', feedback: 'User rejected this action.' });
  });

  it('names the interrupt it settles, so it cannot land on another pending approval', () => {
    expect(buildResumeValue(true, 'int-1')).toEqual({ decision: 'approve', interruptId: 'int-1' });
    expect(buildResumeValue(false, 'int-2')).toEqual({
      decision: 'reject',
      feedback: 'User rejected this action.',
      interruptId: 'int-2',
    });
  });

  it('sends a new message without resume_value', () => {
    const body = buildStreamBody({ messageId: 'm1', chatId: 'c1', query: 'hi', timezone: 'UTC', timestamp: 1 });

    expect(body).toEqual({
      message_id: 'm1',
      chat_id: 'c1',
      query: 'hi',
      action_mode: 'agent',
      agent_config: { enabled_builtin_tools: ['web_search', 'memory'] },
      timezone: 'UTC',
      timestamp: 1,
    });
    expect('resume_value' in body).toBe(false);
  });

  it('leaves out the structured clarification form, which only the web app can answer', () => {
    const { agent_config: agentConfig } = buildStreamBody({
      messageId: 'm1',
      chatId: 'c1',
      query: 'hi',
      timezone: 'UTC',
      timestamp: 1,
    });

    expect(agentConfig.enabled_builtin_tools).not.toContain('structured_clarify');
  });

  it('resumes the same message and chat with an empty query and the answer', () => {
    const resumeValue = buildResumeValue(true);
    const body = buildStreamBody({
      messageId: 'm1',
      chatId: 'c1',
      query: '',
      resumeValue,
      timezone: 'UTC',
      timestamp: 2,
    });

    expect(body).toMatchObject({
      message_id: 'm1',
      chat_id: 'c1',
      query: '',
      action_mode: 'agent',
      agent_config: { enabled_builtin_tools: ['web_search', 'memory'] },
      resume_value: resumeValue,
    });
  });

  it('recognizes only 409 as an interrupt that was settled elsewhere', () => {
    expect(isResumeConflict(409)).toBe(true);
    expect([200, 400, 403, 500].some(isResumeConflict)).toBe(false);
  });
});
