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
const formatTime = (timestampMs: number) => `t${timestampMs}`;

const toolEvent = (
  actionRequests: unknown[],
  extra: { reviewConfigs?: unknown[]; extensions?: Record<string, unknown> } = {},
) => ({ type: 'tool_approval_request', data: { actionRequests, ...extra } });

/** Action requests exactly as the harness builds them (`build_interrupt_payload` with `redact_for_display`). */
const harnessShellAction = (command: string, description: string, explanation?: { en: string; zh: string }) => ({
  action: 'bash_code_execute_tool',
  args: { command },
  description,
  command_spans: [{ startIndex: 0, endIndex: command.length }],
  command_span_risks: ['unknown'],
  command_span_reasons: ['unknown_command'],
  ...(explanation && { plain_explanation: explanation }),
});

const PIP = harnessShellAction('pip install openpyxl', 'Command may modify the workspace', {
  en: 'Install Python packages: openpyxl',
  zh: '安装 Python 包: openpyxl',
});
const CURL = harnessShellAction(
  'curl -sS https://api.example.com/orders -o ~/Documents/orders.json',
  "Domain 'api.example.com' requires approval",
  { en: 'Download from https://api.example.com/orders', zh: '从 https://api.example.com/orders 下载' },
);
const RM = {
  ...harnessShellAction(
    'rm -rf ~/Downloads/old_invoices',
    'Irreversible destructive operation (rm -rf) requires explicit human approval',
    { en: 'Delete: ~/Downloads/old_invoices', zh: '删除: ~/Downloads/old_invoices' },
  ),
  irreversibleDestructive: true,
};
const RM_REVIEW = {
  allowedDecisions: ['approve', 'reject', 'edit'],
  irreversibleDestructive: true,
  hideAllowAlways: true,
  blastRadius: { command: 'rm' },
  snapshotId: null,
};

describe('describeApproval: what the user is asked to approve', () => {
  it('shows a shell command as its plain explanation, the full command and the reason, not the tool name', () => {
    const view = describeApproval(toolEvent([CURL]), { language: 'en-US' });

    expect(view.actions).toEqual([
      {
        summary: 'Download from https://api.example.com/orders',
        body: 'curl -sS https://api.example.com/orders -o ~/Documents/orders.json',
        reason: "Domain 'api.example.com' requires approval",
      },
    ]);
    expect(JSON.stringify(view)).not.toContain('bash_code_execute_tool');
    expect(view.canApprove).toBe(true);
  });

  it.each([
    ['zh-CN', '安装 Python 包: openpyxl'],
    ['zh-TW', '安装 Python 包: openpyxl'],
    ['en-US', 'Install Python packages: openpyxl'],
    ['de', 'Install Python packages: openpyxl'],
  ])('explains the command in the language of the UI (%s)', (language, expected) => {
    expect(describeApproval(toolEvent([PIP]), { language }).actions[0].summary).toBe(expected);
  });

  it('still shows the command when the harness has no explanation for it', () => {
    const view = describeApproval(toolEvent([harnessShellAction('make deploy', 'Command may modify the workspace')]));

    expect(view.actions[0]).toEqual({
      summary: '',
      body: 'make deploy',
      reason: 'Command may modify the workspace',
    });
  });

  it('lists the arguments of a tool that is not a shell command, without naming the internal tool', () => {
    const view = describeApproval(
      toolEvent([
        {
          action: 'file_write_tool',
          args: { path: '/workspace/report.md', append: true, options: { mode: 'w' } },
          description: 'Write outside the allowed roots',
        },
      ]),
    );

    expect(view.actions).toEqual([
      {
        summary: '',
        body: 'path: /workspace/report.md\nappend: true\noptions: {"mode":"w"}',
        reason: 'Write outside the allowed roots',
      },
    ]);
    expect(view.canApprove).toBe(true);
  });

  it('marks where a long argument value was cut, and never approves what it cannot show in full', () => {
    const view = describeApproval(
      toolEvent([{ action: 'file_write_tool', args: { path: '/a.md', content: `# Report\n${'line\n'.repeat(500)}` } }]),
    );

    const [pathLine, contentLine] = view.actions[0].body.split('\n');
    expect(pathLine).toBe('path: /a.md');
    expect(contentLine).toBe('content: # Report');
    expect(view.actions[0].body.split('\n').at(-1)?.endsWith('…')).toBe(true);
    expect(view.canApprove).toBe(false);
    expect(view.blocker).toBe('too_long');
  });

  it('shows a value of exactly the limit in full and lets it be approved', () => {
    const value = 'a'.repeat(300);

    const view = describeApproval(toolEvent([{ action: 'file_write_tool', args: { content: value } }]));

    expect(view.actions[0].body).toBe(`content: ${value}`);
    expect(view.canApprove).toBe(true);
  });

  it('counts a value that is not a string by its JSON text', () => {
    const view = describeApproval(
      toolEvent([{ action: 't', args: { items: Array.from({ length: 200 }, (_, i) => i) } }]),
    );

    expect(view.canApprove).toBe(false);
    expect(view.blocker).toBe('too_long');
  });

  it.each([
    ['no arguments', undefined, ''],
    ['empty arguments', {}, ''],
    ['arguments that are not an object', ['x'], '["x"]'],
  ])('copes with %s', (_label, args, body) => {
    expect(describeApproval(toolEvent([{ action: 't', args }])).actions[0].body).toBe(body);
  });

  it('shows a command of exactly the limit in full and lets it be approved', () => {
    const command = `echo ${'a'.repeat(1995)}`;
    expect(command).toHaveLength(2000);

    const view = describeApproval(toolEvent([harnessShellAction(command, 'r')]));

    expect(view.actions[0].body).toBe(command);
    expect(view.canApprove).toBe(true);
    expect(view.blocker).toBeUndefined();
  });

  it('never approves a command it cannot show in full, so a dangerous tail cannot hide behind the cut', () => {
    const command = `echo ok ${'a'.repeat(2500)}; rm -rf ~`;

    const view = describeApproval(toolEvent([harnessShellAction(command, 'r')]));

    expect(view.actions[0].body).toHaveLength(2000);
    expect(view.actions[0].body.endsWith('…')).toBe(true);
    expect(view.actions[0].body).not.toContain('rm -rf');
    expect(view.canApprove).toBe(false);
    expect(view.blocker).toBe('too_long');
  });

  it('describes every action of the interrupt, because one decision covers all of them', () => {
    const view = describeApproval(toolEvent([PIP, { action: 'file_write_tool', args: { path: '/a' } }]));

    expect(view.kind).toBe('tool');
    expect(view.actions.map((action) => action.body)).toEqual(['pip install openpyxl', 'path: /a']);
  });

  it('never approves an action it has nothing to show for, since that would be approving blind', () => {
    const view = describeApproval(toolEvent([PIP, { action: 'file_write_tool', args: {} }]));

    expect(view.canApprove).toBe(false);
    expect(view.blocker).toBe('no_details');
  });

  it.each([
    ['a reason', { action: 'refresh_tool', description: 'Refresh the connection' }],
    ['an argument', { action: 'refresh_tool', args: { target: 'mail' } }],
  ])('approves an action that shows %s', (_label, request) => {
    expect(describeApproval(toolEvent([request])).canApprove).toBe(true);
  });
});

describe('describeApproval: whether the panel may approve', () => {
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
    expect(view.blocker).toBe('elevated');
  });

  it('only lets the irreversible delete the harness builds be rejected here', () => {
    const view = describeApproval(toolEvent([RM], { reviewConfigs: [RM_REVIEW] }));

    expect(view.actions[0].summary).toBe('Delete: ~/Downloads/old_invoices');
    expect(view.canApprove).toBe(false);
    expect(view.blocker).toBe('elevated');
  });

  it('refuses to approve a browser handover, which needs the live browser view', () => {
    const view = describeApproval(toolEvent([{ action: 'browser' }], { extensions: { displayMode: 'handover' } }));

    expect(view.canApprove).toBe(false);
    expect(view.blocker).toBe('elevated');
  });

  it('still allows approving what the harness sends for an ordinary tool call', () => {
    const view = describeApproval(
      toolEvent([PIP, CURL, { action: 'c', description: 'Run c' }], {
        reviewConfigs: [
          { allowedDecisions: ['approve', 'reject', 'edit'] },
          { allowedDecisions: ['approve', 'reject', 'edit'], hideAllowAlways: true, domainApproval: true },
          null,
        ],
      }),
    );

    expect(view.canApprove).toBe(true);
    expect(view.blocker).toBeUndefined();
  });

  it('ignores switched-off flags', () => {
    const view = describeApproval(
      toolEvent([{ action: 'a', description: 'Run a' }], { reviewConfigs: [{ isSpend: false, blastRadius: null }] }),
    );

    expect(view.canApprove).toBe(true);
  });

  it.each([
    ['carries the interrupt id the event names', 'int-1', 'int-1'],
    ['has none when the event names none', undefined, undefined],
    ['ignores an empty id', '', undefined],
    ['ignores an id that is not a string', 7, undefined],
  ])('%s', (_label, interruptId, expected) => {
    const view = describeApproval({ ...toolEvent([{ action: 'a' }]), interruptId });

    expect(view.interruptId).toBe(expected);
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

describe('describeApproval: when the server settles an unanswered request', () => {
  const withTimeout = (timeout: unknown) => toolEvent([PIP], { extensions: { timeout } });

  it('counts the deadline from the arrival of the event on the panel clock, not from the server clock', () => {
    const view = describeApproval(withTimeout({ seconds: 120, expiresAt: 1, behavior: 'deny' }), { now: 1_000_000 });

    expect(view.deadline).toEqual({ atMs: 1_120_000, behavior: 'deny' });
  });

  it('keeps an automatic approval distinct from an automatic rejection', () => {
    const view = describeApproval(withTimeout({ seconds: 30, behavior: 'allow' }), { now: 0 });

    expect(view.deadline).toEqual({ atMs: 30_000, behavior: 'allow' });
  });

  it.each([
    ['no timeout', undefined],
    ['no seconds', { behavior: 'deny' }],
    ['zero seconds', { seconds: 0, behavior: 'deny' }],
    ['negative seconds', { seconds: -5, behavior: 'deny' }],
    ['seconds that are not a number', { seconds: '120', behavior: 'deny' }],
    ['an unknown behavior', { seconds: 120, behavior: 'escalate' }],
    ['no behavior', { seconds: 120 }],
  ])('states no deadline for %s', (_label, timeout) => {
    expect(describeApproval(withTimeout(timeout)).deadline).toBeUndefined();
  });
});

describe('resolveApprovalCopy', () => {
  it('asks a single action without naming the tool', () => {
    const copy = resolveApprovalCopy(describeApproval(toolEvent([PIP])), translate, formatTime);

    expect(copy).toEqual({
      title: '__approvalTitleSingle__',
      hint: '',
      deadline: '',
      expired: '',
      rejectLabel: '__approvalReject__',
    });
  });

  it('titles a batch by its size', () => {
    const copy = resolveApprovalCopy(describeApproval(toolEvent([PIP, CURL])), translate, formatTime);

    expect(copy.title).toBe('__approvalTitleBatch:2__');
  });

  it.each([
    [
      'an elevated request is approved in the web app',
      toolEvent([RM], { reviewConfigs: [RM_REVIEW] }),
      '__approvalHintElevated__',
    ],
    [
      'a command too long to review is approved in the web app',
      toolEvent([harnessShellAction(`echo ${'a'.repeat(2500)}`, 'r')]),
      '__approvalHintTooLong__',
    ],
    [
      'an action with nothing to show is approved in the web app',
      toolEvent([{ action: 'refresh_tool', args: {} }]),
      '__approvalHintNoDetails__',
    ],
  ])('explains that %s', (_label, event, hint) => {
    const copy = resolveApprovalCopy(describeApproval(event), translate, formatTime);

    expect(copy.hint).toBe(hint);
    expect(copy.rejectLabel).toBe('__approvalReject__');
  });

  it.each([
    ['deny', '__approvalDeadlineDeny:t120000__', '__approvalExpiredDeny__'],
    ['allow', '__approvalDeadlineAllow:t120000__', '__approvalExpiredAllow__'],
  ])('states what happens at the deadline when the default is %s', (behavior, deadline, expired) => {
    const view = describeApproval(toolEvent([PIP], { extensions: { timeout: { seconds: 120, behavior } } }), {
      now: 0,
    });

    const copy = resolveApprovalCopy(view, translate, formatTime);
    expect(copy.deadline).toBe(deadline);
    expect(copy.expired).toBe(expired);
  });

  it('turns an external request into a dismissable notice without technical detail', () => {
    const copy = resolveApprovalCopy(
      describeApproval({ type: 'approval_required', data: { secret: 'payload' } }),
      translate,
      formatTime,
    );

    expect(copy).toEqual({
      title: '__approvalTitleExternal__',
      hint: '__approvalHintExternal__',
      deadline: '',
      expired: '',
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
      multiplexed: false,
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
