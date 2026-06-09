import { describe, expect, it } from 'vitest';

import { buildApprovalDecision } from '@/lib/approval/approvalDecision';

describe('buildApprovalDecision', () => {
  it('builds approve decisions with extensions', () => {
    expect(buildApprovalDecision('approve')).toEqual({
      type: 'approve',
      args: undefined,
      feedback: undefined,
      extensions: { allowAlways: false },
    });
  });

  it('builds reject decisions with feedback and domain allow', () => {
    expect(
      buildApprovalDecision('reject', {
        feedback: 'Batch rejected by user',
        allow_domain: true,
      }),
    ).toEqual({
      type: 'reject',
      args: undefined,
      feedback: 'Batch rejected by user',
      extensions: { allowAlways: false, allowDomain: true },
    });
  });

  it('forwards structured allow_always extensions', () => {
    expect(
      buildApprovalDecision('approve', {
        allow_always: { tool: true, args: true },
      }),
    ).toEqual({
      type: 'approve',
      args: undefined,
      feedback: undefined,
      extensions: { allowAlways: { tool: true, args: true } },
    });
  });

  it('builds edit decisions with edited args', () => {
    expect(
      buildApprovalDecision('edit', {
        edited_args: { ref: 'e2' },
        allow_always: true,
      }),
    ).toEqual({
      type: 'edit',
      args: { ref: 'e2' },
      feedback: undefined,
      extensions: { allowAlways: true },
    });
  });
});
