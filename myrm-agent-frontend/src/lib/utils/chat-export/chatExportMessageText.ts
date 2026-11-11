/**
 * [INPUT] error-handling::redactSensitiveClientText (POS: client-side secret redaction, CWE-312); store/chat/types::Message, Source (type-only).
 * [OUTPUT] ReasoningLayout, MessageLabels; formatReasoning, formatSourcesFootnotes, formatMessageMarkdown, extractMessageTitle.
 * [POS] The text one copied or exported message is made of: its Markdown (reasoning, answer, sources) and the title its file is named after. Pure functions, so the single-message exports of every format and the copy button share one source. The wording of the labels is the caller's, so this module holds no language.
 */
import { redactSensitiveClientText } from '@/lib/utils/error-handling';
import type { Message, Source } from '@/store/chat/types';

const TITLE_MAX_CHARS = 80;

/** How the reasoning sits in the text: folded into a `<details>` the reader can open, or as a labelled quote. */
export type ReasoningLayout = 'fold' | 'quote';

/**
 * The wording of the labelled parts of a copied or exported message. The caller takes it from the interface
 * translations, so the text reads in the language of the interface that made it, with the same words the reader saw on
 * screen.
 */
export interface MessageLabels {
  reasoning: string;
  sources: string;
  /** Stands in for a source that has no address and no name of any kind. */
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

/**
 * A web page is named by its address, else its title. The other kinds carry their name in a field of their own: a wiki
 * hit in its file (with the section, as the interface shows it) or its knowledge base, an MCP call in its skill. A
 * source with none of them gets the caller's stand-in.
 */
function sourceName(source: Source, untitled: string): string {
  if (source.url) {
    return source.url;
  }
  if (source.title) {
    return source.title;
  }
  if (source.filename) {
    return source.section ? `${source.filename} § ${source.section}` : source.filename;
  }
  return source.skill_name || source.kb_name || untitled;
}

/**
 * The block that lists a message's sources, empty when it has none. It starts with the blank line that sets it off from
 * the text before it.
 */
export function formatSourcesFootnotes(
  sources: Source[] | undefined,
  labels: Pick<MessageLabels, 'sources' | 'untitledSource'>,
): string {
  if (!sources || sources.length === 0) {
    return '';
  }
  const lines = sources.map((s, i) => `[${i + 1}] ${sourceName(s, labels.untitledSource)}`);
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
