/**
 * [INPUT]
 * - Transcript text (final or interim)
 *
 * [OUTPUT]
 * - isStopCommand: whether the transcript ends the voice hands-free session
 *
 * [POS]
 * Voice command detection (pure functions, no I/O). Exact-match only so
 * dictation containing these words mid-sentence never triggers.
 */

const STOP_COMMANDS: ReadonlySet<string> = new Set(['stop', 'quit', 'exit', '停止', '停', '结束', '退出']);

const TRAILING_PUNCTUATION = /[.!?。！？，、\s]+$/u;

export function normalizeVoiceCommand(text: string): string {
  return text.trim().toLowerCase().replace(TRAILING_PUNCTUATION, '');
}

export function isStopCommand(text: string): boolean {
  if (!text) {
    return false;
  }
  return STOP_COMMANDS.has(normalizeVoiceCommand(text));
}
