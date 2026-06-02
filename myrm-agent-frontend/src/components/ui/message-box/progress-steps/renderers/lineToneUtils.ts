export type LineTone = 'command' | 'success' | 'error' | 'warning' | 'muted' | 'default';

export const TONE_PATTERNS: [LineTone, RegExp][] = [
  ['command', /^[\s]*[$❯►]\s+\S/],
  ['error', /✖|✗|error|failed|panic|denied|FAIL|fatal|exception|traceback/i],
  ['warning', /warning|warn|deprecated|caution/i],
  ['success', /✔|✓|success|completed|done|passed|PASS|ok\b/i],
  ['muted', /^[\s]*[╭╰╮╯─│┌└┐┘├┤┬┴┼]+|^\s*\d{2,4}[-/]\d{2}/],
];

export const TONE_CLASSES: Record<LineTone, string> = {
  command: 'text-blue-400',
  success: 'text-emerald-400',
  error: 'text-red-400',
  warning: 'text-amber-400',
  muted: 'text-zinc-500',
  default: '',
};

export function getLineTone(line: string): LineTone {
  if (!line.trim()) return 'default';
  for (const [tone, pattern] of TONE_PATTERNS) {
    if (pattern.test(line)) return tone;
  }
  return 'default';
}
