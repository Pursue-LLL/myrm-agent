/**
 * [INPUT]
 * - ApiError from @/lib/api (POS: the failure a terminal request raises; `code` is the HTTP status)
 *
 * [OUTPUT]
 * - MAX_INJECTED_OUTPUT_CHARS: How much of one command's output may be handed to the chat composer
 * - buildTerminalSnippet: Fenced text of a command and the tail of its output
 * - appendToComposer: Adds a snippet after whatever the user already typed
 * - classifyTerminalFailure: Names why a terminal request failed, so the panel can say it in the user's language
 *
 * [POS]
 * Pure helpers of the workbench terminal: what reaches the chat input and how a failed request is explained.
 */

import { ApiError } from '@/lib/api';

export const MAX_INJECTED_OUTPUT_CHARS = 8000;

export type TerminalFailureKind = 'blocked' | 'workspaceUnavailable' | 'timedOut' | 'failed';

interface SnippetInput {
  command: string;
  output: string;
  /** Said once ahead of the output when only its tail is kept. */
  omittedMarker: string;
}

function isLowSurrogate(unit: number): boolean {
  return unit >= 0xdc00 && unit <= 0xdfff;
}

/** The last `limit` characters, started on a line of their own when a line break is close by. */
function tailOf(output: string, limit: number): { text: string; omitted: boolean } {
  if (output.length <= limit) {
    return { text: output, omitted: false };
  }
  let tail = output.slice(-limit);
  const lineBreak = tail.indexOf('\n');
  if (lineBreak >= 0 && lineBreak < limit / 4) {
    tail = tail.slice(lineBreak + 1);
  } else if (isLowSurrogate(tail.charCodeAt(0))) {
    tail = tail.slice(1);
  }
  return { text: tail, omitted: true };
}

/** A fence longer than any backtick run inside the text, so the text cannot close it early. */
function fenceFor(text: string): string {
  const longestRun = (text.match(/`+/g) ?? []).reduce((longest, run) => Math.max(longest, run.length), 0);
  return '`'.repeat(Math.max(3, longestRun + 1));
}

export function buildTerminalSnippet({ command, output, omittedMarker }: SnippetInput): string {
  const { text, omitted } = tailOf(output.trim(), MAX_INJECTED_OUTPUT_CHARS);
  const lines = [`$ ${command}`, ...(omitted ? [omittedMarker] : []), text];
  const body = lines.join('\n');
  const fence = fenceFor(body);
  return `${fence}bash\n${body}\n${fence}`;
}

/** Keeps what the user already typed; ends with a line break so typing can continue below the snippet. */
export function appendToComposer(current: string, snippet: string): string {
  return current.trim() ? `${current.trimEnd()}\n\n${snippet}\n` : `${snippet}\n`;
}

export function classifyTerminalFailure(error: unknown): TerminalFailureKind {
  if (!(error instanceof ApiError)) {
    return 'failed';
  }
  // The request's own deadline raises TIMEOUT_ERROR; the server answers 408 when it stopped the command itself.
  if (error.code === 408 || error.businessCode === 'TIMEOUT_ERROR') {
    return 'timedOut';
  }
  if (error.code === 400) {
    return 'blocked';
  }
  if (error.code === 404) {
    return 'workspaceUnavailable';
  }
  return 'failed';
}
