/**
 * The first characters of a text, counted the way the server counts them.
 *
 * [INPUT]
 * - text: what to cut
 * - max: the most characters to keep
 *
 * [OUTPUT]
 * - firstChars: the first `max` characters of `text`
 *
 * [POS]
 * The one way to cut user text to a length the server enforces by character count (Pydantic `max_length`). An emoji or a
 * rare han character is one character here as it is there, so the cut never leaves half of one, which `String#slice` and
 * the `maxlength` attribute (both count UTF-16 units) cannot promise.
 */

export function firstChars(text: string, max: number): string {
  // `max` characters fit in `2 * max` UTF-16 units, so a long text is not spread into an array whole.
  return Array.from(text.slice(0, max * 2))
    .slice(0, max)
    .join('');
}
