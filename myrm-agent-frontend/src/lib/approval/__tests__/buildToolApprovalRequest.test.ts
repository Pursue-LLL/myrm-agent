import { describe, expect, it } from 'vitest';

import { buildToolApprovalRequest } from '@/lib/approval/buildToolApprovalRequest';

describe('buildToolApprovalRequest', () => {
  it('maps command_spans from harness payload', () => {
    const request = buildToolApprovalRequest({
      action: {
        action: 'bash_code_execute_tool',
        args: { command: 'ls | grep foo' },
        description: 'needs approval',
        command_spans: [
          { startIndex: 0, endIndex: 2 },
          { startIndex: 5, endIndex: 13 },
        ],
        command_span_risks: ['safe', 'unknown'],
        command_span_reasons: ['safe', 'unknown_command'],
      },
      requestId: 'req-1',
      messageId: 'msg-1',
      chatId: 'chat-1',
      actionMode: 'agent',
      extensions: {
        timeout: { seconds: 60, expiresAt: 1_700_000_000 },
        displayMode: 'approval',
      },
    });

    expect(request.commandSpans).toHaveLength(2);
    expect(request.commandSpanRisks).toEqual(['safe', 'unknown']);
    expect(request.commandSpanReasons).toEqual(['safe', 'unknown_command']);
    expect(request.toolName).toBe('bash_code_execute_tool');
  });

  it('maps workspace root from extensions', () => {
    const request = buildToolApprovalRequest({
      action: {
        action: 'bash_code_execute_tool',
        args: { command: 'ls' },
        description: 'needs approval',
      },
      requestId: 'req-2',
      messageId: 'msg-2',
      chatId: 'chat-2',
      actionMode: 'agent',
      extensions: {
        timeout: { seconds: 60, expiresAt: 1_700_000_000 },
        displayMode: 'approval',
        workspaceRoot: '/workspace/demo',
      },
    });

    expect(request.workspaceRoot).toBe('/workspace/demo');
  });
});
