import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const CHAT_STORE_ROOT = resolve(__dirname, '..');

function readSource(relativePath: string): string {
  return readFileSync(resolve(CHAT_STORE_ROOT, relativePath), 'utf8');
}

describe('chat agent binding architecture contracts', () => {
  it('requires finalizeAgentStreamTurn on agent-stream exit paths', () => {
    const finalizeSources: Array<{ file: string; mustContain: string }> = [
      { file: 'streamConsumer.ts', mustContain: 'finalizeAgentStreamTurn' },
      { file: 'messageRequest.ts', mustContain: 'finalizeAgentStreamTurn' },
      { file: '../../lib/approval/resumeApprovalStream.ts', mustContain: 'finalizeAgentStreamTurn' },
      { file: '../../services/chat.ts', mustContain: 'finalizeAgentStreamTurn' },
    ];

    for (const { file, mustContain } of finalizeSources) {
      const source = readSource(file);
      expect(source, file).toContain(mustContain);
    }
  });

  it('forbids silent snapshot refresh from preserving isMessagesLoaded', () => {
    const source = readSource('messageManagement.ts');
    expect(source).not.toContain('preservedIsMessagesLoaded');
    expect(source).toContain('isMessagesLoaded: never preserve');
  });

  it('requires preset resync when agentId already matches during restore', () => {
    const source = readSource('chatAgentSessionRestore.ts');
    expect(source).toContain('agentAlreadyBound');
    expect(source).toContain('securityPreset');
    expect(source).toContain('sessionAgentHydration');
  });
});
