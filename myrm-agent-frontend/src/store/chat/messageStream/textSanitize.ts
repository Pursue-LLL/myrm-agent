/**
 * [OUTPUT]
 * sanitizeStreamText: strips control characters from streamed LLM chunks
 *
 * [POS]
 * Stream text hygiene for reasoning and message SSE payloads.
 */

// eslint-disable-next-line no-control-regex
const UNICODE_CONTROL_RE = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F\uFFFD]/g;

export function sanitizeStreamText(chunk: string): string {
  return chunk.replace(UNICODE_CONTROL_RE, '');
}
