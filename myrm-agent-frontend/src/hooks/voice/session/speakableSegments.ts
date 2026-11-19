/**
 * [INPUT]
 * (no module dependencies)
 *
 * [OUTPUT]
 * extractSpeakableSegments: splits agent reply text into sentence segments ready for TTS
 *
 * [POS]
 * Pure sentence segmenter feeding the voice session TTS queue; a trailing fragment without
 * a terminator is kept as its own segment so the last words of a reply are still spoken.
 */

const SENTENCE_END_PATTERN = /[.!?。！？\n]/;
const TERMINATOR_ONLY_PATTERN = /^[.!?。！？\s]+$/;

export function extractSpeakableSegments(text: string): string[] {
  const segments: string[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    const match = SENTENCE_END_PATTERN.exec(remaining);
    if (match && match.index !== undefined) {
      const segment = remaining.slice(0, match.index + 1).trim();
      if (segment && !TERMINATOR_ONLY_PATTERN.test(segment)) {
        segments.push(segment);
      }
      remaining = remaining.slice(match.index + 1);
    } else {
      break;
    }
  }

  const tail = remaining.trim();
  if (tail && !TERMINATOR_ONLY_PATTERN.test(tail)) {
    segments.push(tail);
  }

  return segments;
}
