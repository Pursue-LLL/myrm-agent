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

  it('carries the stable reason code and its subject beside the English description', () => {
    const request = buildToolApprovalRequest({
      action: {
        action: 'file_read_tool',
        args: { paths: ['/data/a.csv'] },
        description: 'Path outside allowed zones: /data/a.csv',
        reasonCode: 'path_outside_zones',
        reasonSubject: ' /data/a.csv ',
      },
      requestId: 'req-1',
      messageId: 'msg-1',
      chatId: 'chat-1',
      actionMode: 'agent',
      extensions: { timeout: { seconds: 60, expiresAt: 1_700_000_000 }, displayMode: 'approval' },
    });

    expect(request.reason).toBe('Path outside allowed zones: /data/a.csv');
    expect(request.reasonCode).toBe('path_outside_zones');
    expect(request.reasonSubject).toBe('/data/a.csv');
  });

  it('leaves the code out when the harness sent none or one the card has no copy for', () => {
    for (const reasonCode of [undefined, 'a_future_code', 3]) {
      const request = buildToolApprovalRequest({
        action: { action: 'shell', args: {}, description: 'needs approval', reasonCode, reasonSubject: '' },
        requestId: 'req-1',
        messageId: 'msg-1',
        chatId: 'chat-1',
        actionMode: 'agent',
        extensions: { timeout: { seconds: 60, expiresAt: 1_700_000_000 }, displayMode: 'approval' },
      });

      expect(request.reasonCode).toBeUndefined();
      expect(request.reasonSubject).toBeUndefined();
    }
  });

  it('keeps the interrupt the card was announced for', () => {
    const request = buildToolApprovalRequest({
      action: { action: 'bash_code_execute_tool', args: { command: 'ls' }, description: 'needs approval' },
      requestId: 'req-1',
      messageId: 'msg-1',
      chatId: 'chat-1',
      actionMode: 'agent',
      extensions: { timeout: { seconds: 60, expiresAt: 1_700_000_000 }, displayMode: 'approval' },
      interruptId: 'int-1',
    });

    expect(request.interruptId).toBe('int-1');
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

  it('parses plain_explanation from harness payload', () => {
    const request = buildToolApprovalRequest({
      action: {
        action: 'bash_code_execute_tool',
        args: { command: 'rm -rf /tmp/foo' },
        description: 'needs approval',
        plain_explanation: { en: 'Delete files or directories', zh: '删除文件或目录' },
      },
      requestId: 'req-3',
      messageId: 'msg-3',
      chatId: 'chat-3',
      actionMode: 'agent',
      extensions: {
        timeout: { seconds: 60, expiresAt: 1_700_000_000 },
        displayMode: 'approval',
      },
    });

    expect(request.plainExplanation).toEqual({
      en: 'Delete files or directories',
      zh: '删除文件或目录',
    });
  });

  it('returns undefined plainExplanation for invalid payload', () => {
    const request = buildToolApprovalRequest({
      action: {
        action: 'bash_code_execute_tool',
        args: { command: 'ls' },
        description: 'needs approval',
        plain_explanation: 'not-an-object',
      },
      requestId: 'req-4',
      messageId: 'msg-4',
      chatId: 'chat-4',
      actionMode: 'agent',
      extensions: {
        timeout: { seconds: 60, expiresAt: 1_700_000_000 },
        displayMode: 'approval',
      },
    });

    expect(request.plainExplanation).toBeUndefined();
  });

  it('maps execution_intent from harness payload', () => {
    const request = buildToolApprovalRequest({
      action: {
        action: 'bash_code_execute_tool',
        args: {
          command: 'npm install',
          reason: 'Install dependencies before running tests',
        },
        description: 'needs approval',
        execution_intent: 'Install dependencies before running tests',
      },
      requestId: 'req-5',
      messageId: 'msg-5',
      chatId: 'chat-5',
      actionMode: 'agent',
      extensions: {
        timeout: { seconds: 60, expiresAt: 1_700_000_000 },
        displayMode: 'approval',
      },
    });

    expect(request.executionIntent).toBe('Install dependencies before running tests');
  });

  it('maps scriptOperand metadata and protected reviewConfig', () => {
    const request = buildToolApprovalRequest({
      action: {
        action: 'bash',
        args: { command: 'bash deploy.sh' },
        description: 'run script',
        scriptOperandPath: '/repo/deploy.sh',
        scriptOperandHash: 'abc123sha256digest',
      },
      reviewConfig: {
        scriptOperandProtected: true,
      },
      requestId: 'req-6',
      messageId: 'msg-6',
      chatId: 'chat-6',
      actionMode: 'agent',
      extensions: {
        timeout: { seconds: 60, expiresAt: 1_700_000_000 },
        displayMode: 'approval',
      },
    });

    expect(request.scriptOperandPath).toBe('/repo/deploy.sh');
    expect(request.scriptOperandHash).toBe('abc123sha256digest');
    expect(request.scriptOperandProtected).toBe(true);
  });

  it('maps diff from patch or diff arguments in action payload', () => {
    const patchRequest = buildToolApprovalRequest({
      action: {
        action: 'apply_patch',
        args: {
          path: 'src/main.py',
          patch: '--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new',
        },
        description: 'apply patch',
      },
      requestId: 'req-patch',
      messageId: 'msg-patch',
      chatId: 'chat-patch',
      actionMode: 'agent',
      extensions: {
        timeout: { seconds: 60, expiresAt: 1_700_000_000 },
        displayMode: 'approval',
      },
    });
    expect(patchRequest.diff).toBe('--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new');

    const diffRequest = buildToolApprovalRequest({
      action: {
        action: 'edit_file',
        args: {
          path: 'src/config.json',
          diff: '@@ -1 +1 @@\n-1\n+2',
        },
        description: 'edit file',
      },
      requestId: 'req-diff',
      messageId: 'msg-diff',
      chatId: 'chat-diff',
      actionMode: 'agent',
      extensions: {
        timeout: { seconds: 60, expiresAt: 1_700_000_000 },
        displayMode: 'approval',
      },
    });
    expect(diffRequest.diff).toBe('@@ -1 +1 @@\n-1\n+2');
  });

  describe('folders the approval can also grant', () => {
    function requestWith(grantDirectories: unknown, description = 'needs approval') {
      return buildToolApprovalRequest({
        action: {
          action: 'file_read_tool',
          args: { paths: ['/Users/me/Downloads/bill.csv'] },
          description,
          grantDirectories,
        },
        requestId: 'req-grant',
        messageId: 'msg-grant',
        chatId: 'chat-grant',
        actionMode: 'agent',
        extensions: { timeout: { seconds: 60, expiresAt: 1_700_000_000 }, displayMode: 'approval' },
      });
    }

    it('carries the folders the harness planned, whatever language the reason is in', () => {
      const request = requestWith(
        [
          { path: '/Users/me/Downloads', writable: false },
          { path: '/Users/me/reports', writable: true },
        ],
        '路径不在允许的目录内',
      );

      expect(request.grantDirectories).toEqual([
        { path: '/Users/me/Downloads', writable: false },
        { path: '/Users/me/reports', writable: true },
      ]);
    });

    it('offers nothing when the harness planned no folder', () => {
      expect(requestWith(undefined).grantDirectories).toBeUndefined();
      expect(requestWith([]).grantDirectories).toBeUndefined();
    });

    it('drops malformed entries and treats a missing writable flag as read-only', () => {
      const request = requestWith([null, 'x', { path: 7 }, { path: '  ' }, { path: ' /Users/me/Downloads ' }]);

      expect(request.grantDirectories).toEqual([{ path: '/Users/me/Downloads', writable: false }]);
    });

    it('ignores a payload that is not a list', () => {
      expect(requestWith({ path: '/Users/me/Downloads', writable: true }).grantDirectories).toBeUndefined();
    });
  });
});
