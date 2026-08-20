/**
 * [INPUT]
 * — (pure function, no runtime deps)
 *
 * [OUTPUT]
 * composeLearnSlashMessage: Hermes-style three-field → raw `/learn …` string.
 * parseLearnSlashInput / buildLearnSlashMessageFromInput: slash palette helpers.
 *
 * [POS]
 * Learn message composition SSOT for WebUI; server `rewrite_learn_query_if_needed` owns prompt rewrite.
 */

export interface LearnFormInput {
  directory?: string;
  url?: string;
  text?: string;
}

/** Compose raw `/learn …` for server SSOT rewrite (Hermes dashboard pattern). */
export function composeLearnSlashMessage(input: LearnFormInput): string | null {
  const segs: string[] = [];
  const dir = input.directory?.trim() ?? '';
  const url = input.url?.trim() ?? '';
  const text = input.text?.trim() ?? '';
  if (dir) {
    segs.push(`local source: ${dir}`);
  }
  if (url) {
    segs.push(`URL: ${url}`);
  }
  if (text) {
    segs.push(text);
  }
  const composed = segs
    .join('; ')
    .replace(/\s*\n\s*/g, ' ')
    .trim();
  if (!composed) {
    return null;
  }
  return `/learn ${composed}`;
}

/** Strip `/learn` prefix from slash input; empty string means default server args. */
export function parseLearnSlashInput(inputValue: string): string {
  return inputValue.replace(/^\/learn\s*/i, '').trim();
}

export function buildLearnSlashMessageFromInput(inputValue: string): string {
  const args = parseLearnSlashInput(inputValue);
  return args ? `/learn ${args}` : '/learn';
}
