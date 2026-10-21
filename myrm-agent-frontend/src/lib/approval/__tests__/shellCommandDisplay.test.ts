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
    expect(parseCommandSpanReasons(['safe', 'unknown_command'], 2)).toEqual(['safe', 'unknown_command']);
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
  it.each<[command: string, expected: string | null]>([
    ['npm install lodash', 'npm install *'],
    ['ls -la', 'ls -la *'],
    ['curl -sS http://127.0.0.1:9/ALLOWLIST_LIVE_PROBE', 'curl -sS *'],
    ['npm install && rm -rf /', null],
    ['npm install | grep foo', null],
    ['npm install; rm file', null],
    ['npm install\nrm -rf /', null],
    ['npm install\r\nrm -rf /', null],
    ['npm install & rm -rf /', null],
    ['npm install|grep foo', null],
    ['npm install > out.txt', null],
    ['npm install < in.txt', null],
    ['npm install $(rm -rf /)', null],
    ['npm install `id`', null],
    ['npm install "$(id)"', null],
    ['(npm install)', null],
    ["npm install 'oops", null],
    ["npm install 'a;b | c'", 'npm install *'],
    ['npm install "a && b"', 'npm install *'],
    ['npm test 2>&1', 'npm test *'],
    ['npm test >/dev/null 2>&1', 'npm test *'],
    ['npm test # run everything; fast', 'npm test *'],
  ])('deriveCommandPattern parity with harness SSOT vectors: %j', (command, expected) => {
    expect(deriveCommandPattern(command)).toBe(expected);
  });

  /** Keep aligned with `TestCompoundShellDetection` in the harness test file above. */
  it.each([
    'npm install && rm -rf /',
    'npm install | grep foo',
    'npm install; rm file',
    'npm install ;',
    'npm install\nrm -rf /',
    'npm install\rrm -rf /',
    'npm install & rm -rf /',
    'npm install |& tee log',
    'npm install>out.txt',
    'npm install < in.txt',
    "npm install <<< 'x'",
    'npm install `id`',
    'npm install $(id)',
    'npm install "$(id)"',
    'npm install "`id`"',
    '(npm install)',
    "npm install 'unterminated",
    'npm install trailing\\',
    'npm install 2>file',
    'npm install > /dev/null',
    'npm install 3>&1 4>&2',
    "echo a$$'\\' ; touch x '",
  ])('treats %j as more than one plain command', (command) => {
    expect(isCompoundShellCommand(command)).toBe(true);
  });

  it.each([
    'npm install lodash',
    "npm install 'a;b | c && d'",
    'npm install "a; b"',
    'npm install a\\;b',
    'npm install # one; two | three',
    'npm install \\\n --save',
    'echo "$HOME"',
    'echo $HOME ${HOME}',
    "echo $'a;b'",
    "echo a$'\\' ; touch x '",
    'npm test 2>&1',
    'npm test >&2',
    'npm test >/dev/null',
    'npm test 2>/dev/null',
    'npm test &>/dev/null',
    'npm test >/dev/null 2>&1',
    'npm test </dev/null',
    'npm test >>/dev/null',
    '',
    '  \n ',
  ])('treats %j as one plain command', (command) => {
    expect(isCompoundShellCommand(command)).toBe(false);
  });
});
