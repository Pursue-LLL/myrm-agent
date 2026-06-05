import { describe, expect, it } from 'vitest';

import {
  extractShellCommand,
  isShellApprovalTool,
  parseCommandSpans,
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
    expect(zipped[0]).toEqual({ span: spans[1], risk: 'safe' });
    expect(zipped[1]).toEqual({ span: spans[0], risk: 'unknown' });
  });
});
