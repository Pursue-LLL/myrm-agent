import { describe, expect, it } from 'vitest';

import {
  expectedSecurityPresetForAgent,
  isAgentSessionHydrated,
  securityPresetNeedsSync,
  shouldDeferMessagesReadyUntilAgentRestore,
} from '@/store/chat/sessionAgentHydration';
import type { AgentConfig } from '@/store/chat/types';

describe('sessionAgentHydration SSOT', () => {
  it('defers ready when chat has agent_id', () => {
    expect(shouldDeferMessagesReadyUntilAgentRestore('agent-1')).toBe(true);
    expect(shouldDeferMessagesReadyUntilAgentRestore('  ')).toBe(false);
    expect(shouldDeferMessagesReadyUntilAgentRestore(null)).toBe(false);
  });

  it('detects preset drift for bound agent', () => {
    const config = { agentId: 'a1', defaultSecurityPreset: 'accept_edits' } as AgentConfig;
    expect(securityPresetNeedsSync('hitl', config)).toBe(true);
    expect(securityPresetNeedsSync('accept_edits', config)).toBe(false);
  });

  it('isAgentSessionHydrated requires bound agent, preset, and ready flags', () => {
    const config = { agentId: 'a1', defaultSecurityPreset: 'accept_edits' } as AgentConfig;
    expect(
      isAgentSessionHydrated(
        {
          chatId: 'c1',
          agentConfig: config,
          securityPreset: 'accept_edits',
          isMessagesLoaded: true,
          loading: false,
        },
        'a1',
      ),
    ).toBe(true);
    expect(
      isAgentSessionHydrated(
        {
          chatId: 'c1',
          agentConfig: config,
          securityPreset: 'hitl',
          isMessagesLoaded: true,
          loading: false,
        },
        'a1',
      ),
    ).toBe(false);
    expect(expectedSecurityPresetForAgent(config)).toBe('accept_edits');
  });
});
