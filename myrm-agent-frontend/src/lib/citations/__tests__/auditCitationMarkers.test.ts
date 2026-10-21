import { describe, expect, it } from 'vitest';
import { auditCitationMarkers, resolveSourceCountForAudit } from '../auditCitationMarkers';

describe('auditCitationMarkers', () => {
  it('returns null when there are no markers', () => {
    expect(auditCitationMarkers('hello', 2)).toBeNull();
  });

  it('counts valid and unresolved fullwidth markers', () => {
    expect(auditCitationMarkers('A【1】 B【3】', 2)).toEqual({
      totalMarkers: 2,
      valid: 1,
      unresolved: 1,
    });
  });

  it('uses max source index for sparse numbering', () => {
    expect(resolveSourceCountForAudit([{ index: 1 }, { index: 5 }])).toBe(5);
  });
});
