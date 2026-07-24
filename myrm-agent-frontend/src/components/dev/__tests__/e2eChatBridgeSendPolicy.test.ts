import { describe, expect, it } from 'vitest';

import {
  shouldPreserveE2eActionMode,
  shouldRunPrepareAutomationSend,
} from '../e2eChatBridgeSendPolicy';

describe('e2eChatBridgeSendPolicy', () => {
  it('preserves fast and deep_research action modes on send', () => {
    expect(shouldPreserveE2eActionMode('fast')).toBe(true);
    expect(shouldPreserveE2eActionMode('deep_research')).toBe(true);
    expect(shouldPreserveE2eActionMode('agent')).toBe(false);
    expect(shouldPreserveE2eActionMode('agent', true)).toBe(true);
  });

  it('skips prepareAutomationSend when action mode must be preserved', () => {
    expect(shouldRunPrepareAutomationSend(true)).toBe(false);
    expect(shouldRunPrepareAutomationSend(false)).toBe(true);
  });
});
