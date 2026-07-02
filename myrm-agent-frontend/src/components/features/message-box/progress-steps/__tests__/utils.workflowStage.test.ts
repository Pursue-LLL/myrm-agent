import { describe, expect, it } from 'vitest';

import { getStepTitle } from '../utils';
import type { ProgressItem } from '@/store/chat/types';

const t = (key: string) => key;

describe('getStepTitle workflow_stage', () => {
  it('uses notify_message as title for workflow_stage category cards', () => {
    const step: ProgressItem = {
      step_key: 'workflow_stage:analysis',
      notify_message: 'Phase 1: Collecting data',
      status: 'in_progress',
    };
    expect(getStepTitle(step, t)).toBe('Phase 1: Collecting data');
  });
});
