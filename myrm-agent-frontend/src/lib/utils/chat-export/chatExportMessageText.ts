/**
 * [INPUT] error-handling::redactSensitiveClientText (POS: client-side secret redaction, CWE-312); store/chat/types::Message, Source (type-only).
 * [OUTPUT] ReasoningLayout, MessageLabels; formatReasoning, formatMessageMarkdown, extractMessageTitle.
 * [POS] The text one exported message is made of: its Markdown (reasoning, answer, sources) and the title its file is named after. Pure functions, so the single-message exports of every format share one source. The wording of the labels is the caller's, so this module holds no language.
 */
import { redactSensitiveClientText } from '@/lib/utils/error-handling';
import type { Message, Source } from '@/store/chat/types';

const TITLE_MAX_CHARS = 80;

/** How the reasoning sits in the text: folded into a `<details>` the reader can open, or as a labelled quote. */
export type ReasoningLayout = 'fold' | 'quote';

/**
 * The wording of an exported message's labelled parts. The caller takes it from the interface translations, so a file
 * reads in the language of the interface that made it, with the same words the reader saw on screen.
 */
export interface MessageLabels {
  reasoning: string;
  sources: string;
  /** Stands in for a source that has neither an address nor a title. */
  untitledSource: string;
}

/**
 * Markdown folds the reasoning away. The HTML and Word exports are built from the Markdown and both drop the raw HTML
 * in it, which would leave the reasoning as paragraphs in front of the answer, label gone, with nothing to tell the two
 * apart, so those two get a labelled quote.
 */
export function formatReasoning(reasoning: string, layout: ReasoningLayout, label: string): string[] {
  if (layout === 'fold') {
    return ['<details>', `<summary>${label}</summary>`, '', reasoning, '', '</details>', ''];
  }
  return [`> **${label}**`, '>', ...reasoning.split('\n').map((line) => (line ? `> ${line}` : '>')), ''];
}

function formatSourcesFootnotes(sources: Source[] | undefined, labels: MessageLabels): string {
  if (!sources || sources.length === 0) {
    return '';
  }
  const lines = sources.map((s, i) => `[${i + 1}] ${s.url || s.title || labels.untitledSource}`);
  // Two trailing spaces make each source its own line wherever the Markdown is rendered; a plain newline would run
  // them together into one paragraph.
  return `\n\n${labels.sources}:  \n${lines.join('  \n')}`;
}

export function formatMessageMarkdown(
  message: Message,
  includeReasoning: boolean,
  labels: MessageLabels,
  redact = true,
  reasoningLayout: ReasoningLayout = 'fold',
): string {
  const lines: string[] = [];
  const reasoning = redact && message.reasoning ? redactSensitiveClientText(message.reasoning) : message.reasoning;
  if (includeReasoning && reasoning) {
    lines.push(...formatReasoning(reasoning, reasoningLayout, labels.reasoning));
  }
  const content = redact ? redactSensitiveClientText(message.content) : message.content;
  lines.push(content);
  lines.push(formatSourcesFootnotes(message.sources, labels));
  return lines.join('\n').trim();
}

/**
 * What a heading, quote or list item starts with is Markdown syntax, not a word of the title. A marker with nothing
 * after it goes too, so a first line of only `#` leaves no title at all.
 */
const TITLE_BLOCK_MARKERS = /^(?:(?:#{1,6}|[-*+]|\d+[.)])(?:\s+|$)|>\s*)+/;

/** The first `max` characters, an emoji or a rare han character counting as one, so the cut never leaves half of one. */
function firstChars(text: string, max: number): string {
  // `max` characters fit in `2 * max` UTF-16 units, so a long line is not spread into an array whole.
  return Array.from(text.slice(0, max * 2))
    .slice(0, max)
    .join('');
}

/**
 * The file name is drawn from the text the file holds, so an export made with redaction on does not give the secret
 * away through its name. The line is redacted whole before it is cut, so a secret that crosses the cut is not left
 * half visible.
 */
export function extractMessageTitle(message: Message, redact: boolean): string {
  const firstLine = message.content.split('\n', 1)[0];
  const text = redact ? redactSensitiveClientText(firstLine) : firstLine;
  return firstChars(text.trim().replace(TITLE_BLOCK_MARKERS, ''), TITLE_MAX_CHARS) || 'message';
}
