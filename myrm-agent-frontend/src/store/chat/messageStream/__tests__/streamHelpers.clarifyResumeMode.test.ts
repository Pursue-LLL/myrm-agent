/**
 * The clarify resume/legacy decision is owned by one rule, mirroring the server SSOT
 * (`stream_collector_helpers.py`): a deep-research clarification is a legacy route; anything else resumes the run.
 */
import { describe, expect, it } from 'vitest';

import { resolveClarifyIsResumeMode } from '../streamHelpers';

describe('resolveClarifyIsResumeMode', () => {
  it('treats a deep-research clarification as a legacy (non-resume) answer', () => {
    expect(resolveClarifyIsResumeMode('deep_research')).toBe(false);
  });

  it('treats a clarification without a source as a resume, matching the server rule', () => {
    expect(resolveClarifyIsResumeMode(undefined)).toBe(true);
  });

  it('treats any other source as a resume', () => {
    expect(resolveClarifyIsResumeMode('conversation_history')).toBe(true);
  });
});
