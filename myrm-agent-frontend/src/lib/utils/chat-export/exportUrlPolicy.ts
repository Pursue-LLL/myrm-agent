/**
 * [INPUT] hast::Parent, Root (type-only).
 * [OUTPUT] isSafeLinkUrl, rehypeSafeLinks.
 * [POS] Which link targets an exported conversation file may keep: the file is opened outside the app, so a link that runs script would run with the reader's page.
 */
import type { Parent, Root } from 'hast';

/** The only schemes a link in an exported file may open; every other one (javascript:, vbscript:, data:, ...) is shown as text. */
const LINK_PROTOCOLS: ReadonlySet<string> = new Set(['http:', 'https:', 'mailto:', 'tel:']);

/**
 * A target without a scheme counts as relative to this base. Resolving it with the same URL parser the browser uses keeps the
 * verdict identical to what the browser will do, including how it strips tabs, newlines and leading control characters.
 */
const RELATIVE_BASE = 'https://export.invalid/';

export function isSafeLinkUrl(raw: string): boolean {
  try {
    return LINK_PROTOCOLS.has(new URL(raw, RELATIVE_BASE).protocol);
  } catch {
    return false;
  }
}

function unwrapRefusedLinks(parent: Parent): void {
  for (const child of parent.children) {
    if (child.type !== 'element') {
      continue;
    }
    const href = child.properties?.href;
    if (child.tagName === 'a' && typeof href === 'string' && !isSafeLinkUrl(href)) {
      child.tagName = 'span';
      delete child.properties.href;
    }
    unwrapRefusedLinks(child);
  }
}

/** A refused link keeps its text but stops being a link. */
export function rehypeSafeLinks() {
  return (tree: Root): void => unwrapRefusedLinks(tree);
}
