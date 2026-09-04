import { describe, expect, it } from 'vitest';

import {
  buildApprovalDecision,
  extractDirectoryGrantOptimistic,
  resumeDecisionsIncludeDirectoryGrant,
} from '@/lib/approval/approvalDecision';

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

  it('forwards ttl_seconds in extensions as ttlSeconds', () => {
    expect(
      buildApprovalDecision('approve', {
        allow_always: { tool: true, pattern: true },
        ttl_seconds: 3600,
      }),
    ).toEqual({
      type: 'approve',
      args: undefined,
      feedback: undefined,
      extensions: {
        allowAlways: { tool: true, pattern: true },
        ttlSeconds: 3600,
      },
    });
  });

  it('automatically extracts ttlSeconds from allow_always object when ttl_seconds not explicitly passed', () => {
    expect(
      buildApprovalDecision('approve', {
        allow_always: { tool: true, duration: '15m', ttl_seconds: 900 },
      }),
    ).toEqual({
      type: 'approve',
      args: undefined,
      feedback: undefined,
      extensions: {
        allowAlways: { tool: true, duration: '15m', ttl_seconds: 900 },
        ttlSeconds: 900,
      },
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

  it('includes guidance when provided', () => {
    const result = buildApprovalDecision('approve', {
      guidance: 'Use production API',
    });
    expect(result.guidance).toBe('Use production API');
  });

  it('omits guidance when empty', () => {
    const result = buildApprovalDecision('approve', { guidance: '' });
    expect(result.guidance).toBeUndefined();
  });

  it('omits guidance when not provided', () => {
    const result = buildApprovalDecision('approve');
    expect(result.guidance).toBeUndefined();
  });

  it('detects directory grant in resume decisions', () => {
    expect(
      resumeDecisionsIncludeDirectoryGrant([
        buildApprovalDecision('approve', { grant_directory: true, grant_directory_path: '/tmp' }),
      ]),
    ).toBe(true);
    expect(resumeDecisionsIncludeDirectoryGrant([buildApprovalDecision('approve')])).toBe(false);
    expect(resumeDecisionsIncludeDirectoryGrant([buildApprovalDecision('reject')])).toBe(false);
  });

  it('extracts path-ASK optimistic root from grant decisions', () => {
    expect(
      extractDirectoryGrantOptimistic([
        buildApprovalDecision('approve', {
          grant_directory: true,
          grant_directory_path: '/tmp/proj',
          grant_directory_writable: true,
        }),
      ]),
    ).toEqual({ path: '/tmp/proj', writable: true, source: 'path_ask_grant' });
    expect(extractDirectoryGrantOptimistic([buildApprovalDecision('approve')])).toBeUndefined();
  });
});
