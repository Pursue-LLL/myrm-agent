/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import {
  buildResumeValue,
  buildStreamBody,
  describeApproval,
  isResumeConflict,
  resolveApprovalCopy,
} from '../../../../../myrm-agent-extension/src/sidepanel/approval.js';

const translate = (key: string, substitution?: string | number) =>
  substitution === undefined ? `__${key}__` : `__${key}:${substitution}__`;

const toolEvent = (
  actionRequests: unknown[],
  extra: { reviewConfigs?: unknown[]; extensions?: Record<string, unknown> } = {},
) => ({ type: 'tool_approval_request', data: { actionRequests, ...extra } });

describe('describeApproval', () => {
  it('describes every action of the interrupt, because one decision covers all of them', () => {
    const view = describeApproval(
      toolEvent([
        { action: 'file_write_tool', args: { path: '/a' }, description: 'Write /a' },
        { action: 'bash_code_execute_tool', args: { command: 'ls' }, description: '' },
      ]),
    );

    expect(view).toEqual({
      kind: 'tool',
      canApprove: true,
      actions: [
        { name: 'file_write_tool', detail: 'Write /a' },
        { name: 'bash_code_execute_tool', detail: '{"command":"ls"}' },
      ],
    });
  });

  it('truncates a very long detail', () => {
    const view = describeApproval(toolEvent([{ action: 't', args: { blob: 'x'.repeat(1000) } }]));

    expect(view.actions[0].detail).toHaveLength(300);
    expect(view.actions[0].detail.endsWith('…')).toBe(true);
  });

  it.each([
    { isSpend: true, actionDigest: 'd' },
    { requiresDualInsurance: true },
    { sociallyIrreversible: true },
    { irreversibleDestructive: true, blastRadius: { command: 'rm' } },
    { scriptOperandProtected: true },
    { smartDenied: true },
    { batchImpactSummary: '3 files' },
    { recoveryHint: 'restore from snapshot' },
    { autoModeSuspended: 'budget' },
    { someFutureGuard: true },
    { allowedDecisions: ['reject'] },
  ])('refuses to approve when any action carries %j, and fails closed on keys it does not know', (config) => {
    const view = describeApproval(toolEvent([{ action: 'a' }, { action: 'b' }], { reviewConfigs: [{}, config] }));

    expect(view.kind).toBe('tool');
    expect(view.canApprove).toBe(false);
  });

  it('refuses to approve a browser handover, which needs the live browser view', () => {
    const view = describeApproval(toolEvent([{ action: 'browser' }], { extensions: { displayMode: 'handover' } }));

    expect(view.canApprove).toBe(false);
  });

  it('still allows approving what the harness sends for an ordinary tool call', () => {
    const view = describeApproval(
      toolEvent([{ action: 'a' }, { action: 'b' }, { action: 'c' }], {
        reviewConfigs: [
          { allowedDecisions: ['approve', 'reject', 'edit'] },
          { allowedDecisions: ['approve', 'reject', 'edit'], hideAllowAlways: true, domainApproval: true },
          null,
        ],
      }),
    );

    expect(view.canApprove).toBe(true);
  });

  it('ignores switched-off flags', () => {
    const view = describeApproval(
      toolEvent([{ action: 'a' }], { reviewConfigs: [{ isSpend: false, blastRadius: null }] }),
    );

    expect(view.canApprove).toBe(true);
  });

  it.each([
    { type: 'approval_required', data: { approval_id: 'x' } },
    { type: 'tool_approval_request', data: { actionRequests: [] } },
    { type: 'tool_approval_request', data: {} },
    { type: 'tool_approval_request' },
  ])('leaves anything the panel cannot answer to the web app: %j', (event) => {
    expect(describeApproval(event)).toEqual({ kind: 'external', actions: [], canApprove: false });
  });
});

describe('resolveApprovalCopy', () => {
  it('titles a single action by its tool name and shows the detail', () => {
    const copy = resolveApprovalCopy(
      describeApproval(toolEvent([{ action: 'file_write_tool', description: 'Write /a' }])),
      translate,
    );

    expect(copy).toEqual({
      title: '__approvalTitleSingle:file_write_tool__',
      detail: 'file_write_tool: Write /a',
      hint: '',
      rejectLabel: '__approvalReject__',
    });
  });

  it('titles a batch by its size and lists every action', () => {
    const copy = resolveApprovalCopy(
      describeApproval(
        toolEvent([
          { action: 'a', description: 'one' },
          { action: 'b', description: 'two' },
        ]),
      ),
      translate,
    );

    expect(copy.title).toBe('__approvalTitleBatch:2__');
    expect(copy.detail).toBe('a: one\nb: two');
  });

  it('explains that an elevated request is approved in the web app', () => {
    const copy = resolveApprovalCopy(
      describeApproval(toolEvent([{ action: 'a', description: 'd' }], { reviewConfigs: [{ isSpend: true }] })),
      translate,
    );

    expect(copy.hint).toBe('__approvalHintElevated__');
    expect(copy.rejectLabel).toBe('__approvalReject__');
  });

  it('turns an external request into a dismissable notice without technical detail', () => {
    const copy = resolveApprovalCopy(
      describeApproval({ type: 'approval_required', data: { secret: 'payload' } }),
      translate,
    );

    expect(copy).toEqual({
      title: '__approvalTitleExternal__',
      detail: '',
      hint: '__approvalHintExternal__',
      rejectLabel: '__approvalDismiss__',
    });
  });
});

describe('resume request', () => {
  it('approves with the one-decision shape the harness applies to every action', () => {
    expect(buildResumeValue(true)).toEqual({ decision: 'approve' });
  });

  it('rejects with the same denial reason the web app sends', () => {
    expect(buildResumeValue(false)).toEqual({ decision: 'reject', feedback: 'User rejected this action.' });
  });

  it('sends a new message without resume_value', () => {
    const body = buildStreamBody({ messageId: 'm1', chatId: 'c1', query: 'hi', timezone: 'UTC', timestamp: 1 });

    expect(body).toEqual({
      message_id: 'm1',
      chat_id: 'c1',
      query: 'hi',
      action_mode: 'agent',
      multiplexed: false,
      timezone: 'UTC',
      timestamp: 1,
    });
    expect('resume_value' in body).toBe(false);
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
      resume_value: resumeValue,
    });
  });

  it('recognizes only 409 as an interrupt that was settled elsewhere', () => {
    expect(isResumeConflict(409)).toBe(true);
    expect([200, 400, 403, 500].some(isResumeConflict)).toBe(false);
  });
});
