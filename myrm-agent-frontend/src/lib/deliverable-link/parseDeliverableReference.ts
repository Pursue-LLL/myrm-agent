/**
 * Parse assistant-authored deliverable references for Markdown linkification.
 *
 * [INPUT] Raw token from inline code or markdown links.
 * [OUTPUT] DeliverableReference discriminated union or null.
 * [POS] FE-only; workspace paths resolve via /files/browse/content + chat_id.
 */

export type DeliverableReference =
  { kind: 'workspace'; path: string } | { kind: 'artifact'; id: string } | { kind: 'file_id'; id: string };

const ARTIFACT_PREFIX = 'artifact:';

/** Matches @file_001 style harness aliases (resolved via message artifacts short_file_id). */
const FILE_ID_RE = /^@file_\d+$/;

function hasFileExtension(segment: string): boolean {
  return /\.[a-zA-Z0-9]{1,12}$/.test(segment);
}

/**
 * Heuristic: workspace-relative path vs arbitrary inline code token.
 * Requires a slash or a dotted extension — avoids linking bare words like `config`.
 */
export function looksLikeWorkspacePath(raw: string): boolean {
  const trimmed = raw.trim();
  if (!trimmed || /\s/.test(trimmed)) {
    return false;
  }
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return false;
  }
  const normalized = trimmed.startsWith('workspace/') ? trimmed.slice('workspace/'.length) : trimmed;
  if (!normalized || normalized.startsWith('.')) {
    return false;
  }
  return normalized.includes('/') || hasFileExtension(normalized);
}

export function parseDeliverableReference(raw: string): DeliverableReference | null {
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }

  if (trimmed.toLowerCase().startsWith(ARTIFACT_PREFIX)) {
    const id = trimmed.slice(ARTIFACT_PREFIX.length).trim();
    if (id.length > 0) {
      return { kind: 'artifact', id };
    }
    return null;
  }

  if (FILE_ID_RE.test(trimmed)) {
    return { kind: 'file_id', id: trimmed };
  }

  if (looksLikeWorkspacePath(trimmed)) {
    const path = trimmed.startsWith('workspace/') ? trimmed : trimmed;
    return { kind: 'workspace', path };
  }

  return null;
}

export function normalizeWorkspaceBrowsePath(path: string): string {
  return path.startsWith('workspace/') ? path.slice('workspace/'.length) : path;
}
