import { describe, expect, it } from 'vitest';

import { isStatusProgressStep } from '../statusStreamProgressSteps';

describe('statusStreamProgressSteps allowed_tools recovery', () => {
  it('recognizes allowed_tools_rejected_recovery as a progress step', () => {
    expect(isStatusProgressStep('allowed_tools_rejected_recovery')).toBe(true);
  });
});
