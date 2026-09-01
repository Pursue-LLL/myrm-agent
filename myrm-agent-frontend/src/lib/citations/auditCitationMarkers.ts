export interface CitationAuditSnapshot {
  totalMarkers: number;
  valid: number;
  unresolved: number;
}

export function resolveSourceCountForAudit(sources: ReadonlyArray<{ index?: number }>): number {
  let count = sources.length;
  for (const source of sources) {
    if (typeof source.index === 'number' && source.index > count) {
      count = source.index;
    }
  }
  return count;
}

const CITATION_FULLWIDTH_RE = /\u3010(\d+)\u3011/g;

/** Match harness `audit_citation_markers` (fullwidth 【N】 only). */
export function auditCitationMarkers(text: string, sourceCount: number): CitationAuditSnapshot | null {
  if (sourceCount <= 0 || !text.trim()) {
    return null;
  }

  const markers = [...text.matchAll(CITATION_FULLWIDTH_RE)].map((match) => match[1]);
  if (markers.length === 0) {
    return null;
  }

  let valid = 0;
  let unresolved = 0;
  for (const numStr of markers) {
    const n = Number.parseInt(numStr, 10);
    if (Number.isFinite(n) && n >= 1 && n <= sourceCount) {
      valid += 1;
    } else {
      unresolved += 1;
    }
  }

  return { totalMarkers: markers.length, valid, unresolved };
}
