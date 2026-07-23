import { describe, expect, it } from 'vitest';

import {
  deriveCommandPattern,
  extractShellCommand,
  getShellEditInputEntries,
  isCompoundShellCommand,
  isShellApprovalTool,
  mergeShellEditedArgs,
  parseCommandSpanReasons,
  parseCommandSpans,
  stripShellApprovalMetadata,
  zipSpansWithRisks,
} from '@/lib/approval/shellCommandDisplay';

describe('shellCommandDisplay', () => {
  it('detects shell approval tools', () => {
    expect(isShellApprovalTool('bash_code_execute_tool')).toBe(true);
    expect(isShellApprovalTool('grep_tool')).toBe(false);
  });

  it('extracts command text from args', () => {
    expect(extractShellCommand({ command: 'ls -la' })).toBe('ls -la');
    expect(extractShellCommand({ code: 'echo hi' })).toBe('echo hi');
  });

  it('parses valid command spans', () => {
    const command = 'ls | grep foo';
    const spans = parseCommandSpans(
      [
        { startIndex: 0, endIndex: 2 },
        { startIndex: 5, endIndex: 13 },
      ],
      command.length,
    );
    expect(spans).toHaveLength(2);
  });

  it('rejects invalid spans', () => {
    expect(parseCommandSpans([{ startIndex: -1, endIndex: 2 }], 10)).toBeUndefined();
    expect(parseCommandSpans([{ startIndex: 0, endIndex: 99 }], 10)).toBeUndefined();
  });

  it('keeps risk aligned when spans are unsorted', () => {
    const spans = [
      { startIndex: 5, endIndex: 13 },
      { startIndex: 0, endIndex: 2 },
    ];
    const risks: Array<'safe' | 'unknown'> = ['unknown', 'safe'];
    const zipped = zipSpansWithRisks(spans, risks);
    expect(zipped[0]).toEqual({ span: spans[1], risk: 'safe', reason: undefined });
    expect(zipped[1]).toEqual({ span: spans[0], risk: 'unknown', reason: undefined });
  });

  it('parses command span reasons', () => {
    expect(
      parseCommandSpanReasons(['safe', 'unknown_command'], 2),
    ).toEqual(['safe', 'unknown_command']);
    expect(parseCommandSpanReasons(['safe', 'bad_code'], 2)).toBeUndefined();
  });

  it('filters shell metadata from edit entries', () => {
    const entries = getShellEditInputEntries({
      command: 'ls -la',
      command_spans: [{ startIndex: 0, endIndex: 5 }],
      command_span_risks: ['safe'],
      command_span_reasons: ['safe'],
    });
    expect(entries).toEqual([['command', 'ls -la']]);
  });

  it('includes timeout and reason in edit entries', () => {
    const keys = getShellEditInputEntries({
      command: 'npm install',
      reason: 'install deps',
      timeout: 300,
    }).map(([key]) => key);
    expect(keys).toEqual(['command', 'reason', 'timeout']);
  });

  it('mergeShellEditedArgs preserves non-edited fields and strips metadata', () => {
    const merged = mergeShellEditedArgs(
      {
        command: 'ls',
        reason: 'list files',
        timeout: 120,
        run_in_background: true,
        command_spans: [{ startIndex: 0, endIndex: 2 }],
        command_span_risks: ['safe'],
      },
      { command: 'pwd' },
    );
    expect(merged).toEqual({
      command: 'pwd',
      reason: 'list files',
      timeout: 120,
      run_in_background: true,
    });
  });

  it('stripShellApprovalMetadata removes span fields only', () => {
    expect(
      stripShellApprovalMetadata({
        command: 'ls',
        command_span_reasons: ['safe'],
      }),
    ).toEqual({ command: 'ls' });
  });

  it('derives conservative command patterns for preview', () => {
    expect(deriveCommandPattern('npm install lodash')).toBe('npm install *');
    expect(deriveCommandPattern('ls -la')).toBe('ls -la *');
    expect(deriveCommandPattern('npm install && rm -rf /')).toBeNull();
  });

  /** Keep aligned with myrm-agent-harness/tests/agent/security/test_command_allowlist_pattern.py */
  it('deriveCommandPattern parity with harness SSOT vectors', () => {
    const vectors: Array<{ command: string; expected: string | null }> = [
      { command: 'npm install lodash', expected: 'npm install *' },
      { command: 'ls -la', expected: 'ls -la *' },
      { command: 'curl -sS http://127.0.0.1:9/ALLOWLIST_LIVE_PROBE', expected: 'curl -sS *' },
      { command: 'npm install && rm -rf /', expected: null },
      { command: 'npm install | grep foo', expected: null },
      { command: 'npm install; rm file', expected: null },
    ];
    for (const { command, expected } of vectors) {
      expect(deriveCommandPattern(command)).toBe(expected);
    }
  });

  it('detects compound shell commands', () => {
    expect(isCompoundShellCommand('npm install')).toBe(false);
    expect(isCompoundShellCommand('npm install | grep foo')).toBe(true);
  });
});
