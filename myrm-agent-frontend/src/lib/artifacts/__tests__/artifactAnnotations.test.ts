import { describe, expect, it } from 'vitest';
import {
  buildAnchor,
  composeReviewMessage,
  excerptLines,
  hashExcerpt,
  relocateAnchor,
  verifyRevisionLocality,
  type AnnotationAnchor,
} from '../artifactAnnotations';

const CONTENT = ['# Title', '', 'First paragraph here.', 'Second paragraph here.', ''].join('\n');

describe('hashExcerpt', () => {
  it('is stable and hex', () => {
    expect(hashExcerpt('abc')).toBe(hashExcerpt('abc'));
    expect(hashExcerpt('abc')).toMatch(/^[0-9a-f]+$/);
    expect(hashExcerpt('abc')).not.toBe(hashExcerpt('abd'));
  });
});

describe('excerptLines', () => {
  it('extracts 1-based ranges', () => {
    expect(excerptLines(CONTENT, 3, 3)).toBe('First paragraph here.');
  });

  it('treats -1 as whole document', () => {
    expect(excerptLines(CONTENT, -1, -1)).toBe(CONTENT);
  });
});

describe('buildAnchor', () => {
  it('carries hash and short excerpt', () => {
    const anchor = buildAnchor(CONTENT, 3, 4);
    expect(anchor.textHash).toBe(hashExcerpt('First paragraph here.\nSecond paragraph here.'));
    expect(anchor.excerpt.length).toBeLessThanOrEqual(120);
  });
});

describe('relocateAnchor', () => {
  it('finds moved excerpts by content', () => {
    const anchor = buildAnchor(CONTENT, 3, 3);
    const revised = ['# Title', 'New intro line.', '', 'First paragraph here.', ''].join('\n');
    expect(relocateAnchor(revised, anchor)).toEqual({ startLine: 4, endLine: 4 });
  });

  it('returns null when the excerpt is gone', () => {
    const anchor = buildAnchor(CONTENT, 3, 3);
    expect(relocateAnchor('# Totally different\ntext here\n', anchor)).toBeNull();
  });
});

describe('composeReviewMessage', () => {
  it('packs anchor, original and intent', () => {
    const anchor: AnnotationAnchor = {
      startLine: 3,
      endLine: 3,
      textHash: 'abc123',
      excerpt: 'First paragraph here.',
    };
    const msg = composeReviewMessage({ artifactName: 'plan.md', annotations: [{ anchor, intent: 'Fix the date' }] });
    expect(msg).toContain('[artifact-review: plan.md]');
    expect(msg).toContain('lines 3-3');
    expect(msg).toContain('Fix the date');
    expect(msg).toContain('Revise ONLY the annotated sections');
  });
});

describe('verifyRevisionLocality', () => {
  it('passes when only annotated lines changed', () => {
    const anchor: AnnotationAnchor = { startLine: 3, endLine: 3, textHash: 'x', excerpt: 'y' };
    const revised = CONTENT.replace('First paragraph here.', 'First paragraph fixed.');
    expect(verifyRevisionLocality(CONTENT, revised, [anchor])).toEqual({ local: true, outsideLines: [] });
  });

  it('flags changes outside annotated ranges', () => {
    const anchor: AnnotationAnchor = { startLine: 3, endLine: 3, textHash: 'x', excerpt: 'y' };
    const revised = CONTENT.replace('Second paragraph here.', 'Second paragraph edited.');
    const verdict = verifyRevisionLocality(CONTENT, revised, [anchor]);
    expect(verdict.local).toBe(false);
    expect(verdict.outsideLines).toEqual([4]);
  });

  it('permits anything for whole-block anchors', () => {
    const anchor: AnnotationAnchor = { startLine: -1, endLine: -1, textHash: 'x', excerpt: 'y' };
    expect(verifyRevisionLocality(CONTENT, 'completely new', [anchor]).local).toBe(true);
  });
});
