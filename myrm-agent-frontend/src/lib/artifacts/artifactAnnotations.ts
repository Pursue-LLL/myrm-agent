'use client';

/**
 * Artifact inline annotations: anchor hashing, fuzzy relocation, review message
 * assembly and revision diff verification.
 *
 * Annotations attach to a specific artifact version. Anchors carry a content
 * hash plus a short excerpt so a later revision can relocate them even after
 * line numbers shift. Nothing here touches the model prompt: the anchor +
 * original text + user intent are necessary task context, and locality is
 * enforced by verifyRevisionLocality (code), not by prose prohibitions.
 */

export interface AnnotationAnchor {
  /** 1-based start line in the annotated version, -1 for whole-block. */
  startLine: number;
  /** 1-based end line (inclusive), -1 for whole-block. */
  endLine: number;
  /** djb2 hash of the anchored excerpt, hex. */
  textHash: string;
  /** First 120 chars of the anchored excerpt for human display. */
  excerpt: string;
}

export interface ArtifactAnnotation {
  id: string;
  artifactId: string;
  versionId: string;
  anchor: AnnotationAnchor;
  /** What the user wants changed. */
  intent: string;
  status: 'open' | 'submitted' | 'resolved';
  createdAt: string;
}

export function hashExcerpt(text: string): string {
  let hash = 5381;
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) + hash + text.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(16);
}

export function excerptLines(content: string, startLine: number, endLine: number): string {
  const lines = content.split('\n');
  const from = Math.max(0, startLine - 1);
  const to = endLine < 0 ? lines.length : Math.min(lines.length, endLine);
  return lines.slice(from, to).join('\n');
}

export function buildAnchor(content: string, startLine: number, endLine: number): AnnotationAnchor {
  const excerpt = excerptLines(content, startLine, endLine);
  return {
    startLine,
    endLine,
    textHash: hashExcerpt(excerpt),
    excerpt: excerpt.slice(0, 120),
  };
}

/**
 * Relocate an anchor in revised content. Returns the new 1-based line range,
 * or null when the excerpt no longer exists (anchor drifted beyond recovery).
 */
export function relocateAnchor(
  revisedContent: string,
  anchor: AnnotationAnchor,
): { startLine: number; endLine: number } | null {
  const lines = revisedContent.split('\n');
  const anchorLines = anchor.excerpt.split('\n').filter((l) => l.trim().length > 0);
  if (anchorLines.length === 0) {
    return null;
  }
  const first = anchorLines[0].trim();
  for (let i = 0; i < lines.length; i += 1) {
    const candidate = lines[i].trim();
    if (candidate.length === 0) {
      continue;
    }
    if (candidate === first || candidate.includes(first) || first.includes(candidate)) {
      const span = Math.max(anchor.endLine - anchor.startLine, 0);
      return { startLine: i + 1, endLine: i + 1 + span };
    }
  }
  if (hashExcerpt(revisedContent) === anchor.textHash) {
    return { startLine: anchor.startLine, endLine: anchor.endLine };
  }
  return null;
}

export interface ReviewPayload {
  artifactName: string;
  annotations: { anchor: AnnotationAnchor; intent: string }[];
}

/**
 * Assemble the structured follow-up message that carries annotations back to
 * the producing agent. Machine-readable block first, human sentence last.
 */
export function composeReviewMessage(payload: ReviewPayload): string {
  const blocks = payload.annotations.map((a, index) => {
    const range =
      a.anchor.startLine < 0 ? 'whole document' : `lines ${a.anchor.startLine}-${a.anchor.endLine}`;
    return [
      `--- annotation ${index + 1} (${range}, hash ${a.anchor.textHash}) ---`,
      `ORIGINAL:\n${a.anchor.excerpt}`,
      `REQUEST: ${a.intent}`,
    ].join('\n');
  });
  return [
    `[artifact-review: ${payload.artifactName}]`,
    ...blocks,
    'Revise ONLY the annotated sections above; leave everything else unchanged.',
  ].join('\n\n');
}

export interface LocalityVerdict {
  /** True when every changed line falls inside an annotated range. */
  local: boolean;
  /** Changed line numbers outside all annotated ranges. */
  outsideLines: number[];
}

/**
 * Verify a revision stayed local: diff old vs new content line by line and
 * check that every changed line belongs to an annotated range. Whole-block
 * annotations ([-1, -1]) permit any change.
 */
export function verifyRevisionLocality(
  oldContent: string,
  newContent: string,
  anchors: AnnotationAnchor[],
): LocalityVerdict {
  if (anchors.some((a) => a.startLine < 0)) {
    return { local: true, outsideLines: [] };
  }
  const oldLines = oldContent.split('\n');
  const newLines = newContent.split('\n');
  const maxLen = Math.max(oldLines.length, newLines.length);
  const outsideLines: number[] = [];
  for (let i = 0; i < maxLen; i += 1) {
    if (oldLines[i] !== newLines[i]) {
      const lineNo = i + 1;
      const covered = anchors.some((a) => lineNo >= a.startLine && lineNo <= Math.max(a.endLine, a.startLine));
      if (!covered) {
        outsideLines.push(lineNo);
      }
    }
  }
  return { local: outsideLines.length === 0, outsideLines };
}
