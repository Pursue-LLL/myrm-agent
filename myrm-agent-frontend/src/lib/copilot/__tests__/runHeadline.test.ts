import { describe, expect, it } from 'vitest';

import { resolveRunDigestHeadline } from '@/lib/copilot/runHeadline';
import type { RunDigest } from '@/services/copilot';

const t = (key: string, values?: Record<string, string | number>) => {
  if (key === 'headlineRunning' && values) {
    return `Step ${values.step}: ${values.tool}`;
  }
  if (key === 'headlineWaitingApproval' && values) {
    return `Waiting (${values.count})`;
  }
  return key;
};

describe('resolveRunDigestHeadline', () => {
  it('returns running headline from structured fields', () => {
    const digest: RunDigest = {
      chat_id: 'c1',
      phase: 'running',
      step_count: 2,
      current_tool: 'grep',
      current_step_key: 'k1',
      pending_approval_count: 0,
      elapsed_seconds: 5,
      headline: 'Step 2: grep',
      recent_steps: [],
      updated_at: '',
    };
    expect(resolveRunDigestHeadline(digest, t)).toBe('Step 2: grep');
  });

  it('returns fallback when digest is null', () => {
    expect(resolveRunDigestHeadline(null, t)).toBe('runningFallback');
  });
});
