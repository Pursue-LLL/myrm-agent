/**
 * [INPUT]
 * @/store/chat/types::Source (POS: Chat state and SSE event type definitions, type-only)
 *
 * [OUTPUT]
 * SourceKind, NamedSource, SectionLabeler: the kinds of source, the fields that name one, and how a wiki section is worded
 * sourceKind: Which kind a source is shown as
 * sourceName: What a source is called, or undefined when it carries no name
 *
 * [POS]
 * SSOT for which field of a source carries its name. The source rows, the citation popovers, the copied text and the
 * exports all call a source the same thing, so a kind of source gains a name in one place.
 */

import type { Source } from '@/store/chat/types';

export type SourceKind = 'knowledge' | 'conversation' | 'mcp' | 'web';

type KindFields = Partial<Pick<Source, 'type' | 'kb_name' | 'skill_name'>>;

/** The fields that name a source, each optional, so a source read back from a stored export is named the same way. */
export type NamedSource = KindFields & Partial<Pick<Source, 'title' | 'filename' | 'section'>>;

/** Words a wiki section the way the interface does. */
export type SectionLabeler = (section: string) => string;

/**
 * The kind a source is shown as. A knowledge-base name or a skill name settles the kind whatever `type` says, so a
 * source whose type is missing still lands with its own kind.
 */
export function sourceKind(source: KindFields): SourceKind {
  if (source.type === 'knowledge' || source.kb_name) {
    return 'knowledge';
  }
  if (source.type === 'conversation_history') {
    return 'conversation';
  }
  if (source.type === 'mcp' || source.skill_name) {
    return 'mcp';
  }
  return 'web';
}

/**
 * What a source is called, or undefined when it carries no name, so each caller picks the stand-in that suits where it
 * speaks. Each kind keeps its name in a field of its own: a wiki hit in its file (with the section) or else its
 * knowledge base, an MCP call in its skill, a past conversation and a web page in their title.
 */
export function sourceName(
  source: NamedSource,
  sectionLabel: SectionLabeler = (section) => section,
): string | undefined {
  switch (sourceKind(source)) {
    case 'knowledge':
      if (!source.filename) {
        return source.kb_name || undefined;
      }
      return source.section ? `${source.filename} § ${sectionLabel(source.section)}` : source.filename;
    case 'mcp':
      return source.skill_name || undefined;
    case 'conversation':
    case 'web':
      return source.title || undefined;
  }
}
