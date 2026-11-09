/**
 * [INPUT]
 * @/store/chat/types::Source (POS: Chat state and SSE event type definitions)
 * @/store/chat/messageStream/streamHelpers::mergeMessageSources (POS: Shared utilities for messageStream/handlers/* event slices)
 *
 * [OUTPUT]
 * buildCitationSources: The sources the citation markers of one message resolve against
 *
 * [POS]
 * Citation source resolver of an answer. SSOT for which source a marker number names when the message and the
 * messages before it both carry sources.
 */

import type { Source } from '@/store/chat/types';
import { mergeMessageSources } from '@/store/chat/messageStream/streamHelpers';

/**
 * The sources a message's citation markers resolve against, ordered by number.
 *
 * A marker names the message's own source with that number first. An answer may also cite a page an earlier turn
 * found, so a number the message does not have is taken from the nearest earlier message that has it. A number is
 * taken once: a source farther back never replaces the one a nearer message gave it.
 */
export function buildCitationSources(earlier: ReadonlyArray<{ sources?: Source[] }>, own: Source[]): Source[] {
  const resolved = mergeMessageSources([], own);
  const taken = new Set(resolved.map((source) => source.index));
  for (let position = earlier.length - 1; position >= 0; position--) {
    for (const source of earlier[position].sources ?? []) {
      const number = Number(source.index);
      if (number > 0 && !taken.has(number)) {
        taken.add(number);
        resolved.push({ ...source, index: number });
      }
    }
  }
  return resolved.sort((a, b) => a.index - b.index);
}
