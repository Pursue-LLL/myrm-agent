import { describe, it, expect } from 'vitest';
import {
  extractDomain,
  calculateSourceQualityMatrix,
  formatPayloadBytes,
  formatLatency,
  getScoreTierBadgeColor,
  summarizeSearchAuditSession,
} from '../searchAuditEngine';
import { SubQueryTrace, AuditCitationItem } from '../searchAuditTypes';

describe('searchAuditEngine', () => {
  it('extracts domain correctly from urls', () => {
    expect(extractDomain('https://arxiv.org/abs/2301.12345')).toBe('arxiv.org');
    expect(extractDomain('https://github.com/openai/evals')).toBe('github.com');
    expect(extractDomain('invalid-url')).toBe('unknown.source');
  });

  it('calculates academic source quality with high authority score', () => {
    const qm = calculateSourceQualityMatrix('https://arxiv.org/abs/2301.12345', true, false);
    expect(qm.tier).toBe('academic');
    expect(qm.authorityScore).toBe(98);
    expect(qm.compositeScore).toBeGreaterThanOrEqual(90);
    expect(qm.verificationBadge).toContain('CCF/SCI');
  });

  it('calculates official code repository quality score', () => {
    const qm = calculateSourceQualityMatrix('https://github.com/facebook/react', true, false);
    expect(qm.tier).toBe('official_code');
    expect(qm.authorityScore).toBe(94);
    expect(qm.compositeScore).toBeGreaterThanOrEqual(88);
  });

  it('calculates sec and financial report authority score', () => {
    const qm = calculateSourceQualityMatrix('https://www.sec.gov/edgar/searchedgar/companysearch', true, false);
    expect(qm.tier).toBe('sec_finance');
    expect(qm.authorityScore).toBe(96);
    expect(qm.compositeScore).toBeGreaterThanOrEqual(90);
  });

  it('penalizes score when source is truncated or contains AI rewrite', () => {
    const original = calculateSourceQualityMatrix('https://techcrunch.com/2026/ai', true, false);
    const degraded = calculateSourceQualityMatrix('https://techcrunch.com/2026/ai', false, true);

    expect(degraded.signalToNoiseScore).toBeLessThan(original.signalToNoiseScore);
    expect(degraded.firstHandScore).toBeLessThan(original.firstHandScore);
    expect(degraded.compositeScore).toBeLessThan(original.compositeScore);
  });

  it('formats payload bytes and latencies', () => {
    expect(formatPayloadBytes(0)).toBe('0 B');
    expect(formatPayloadBytes(512)).toBe('512 B');
    expect(formatPayloadBytes(2048)).toBe('2.0 KB');
    expect(formatPayloadBytes(2097152)).toBe('2.00 MB');

    expect(formatLatency(450)).toBe('450 ms');
    expect(formatLatency(1500)).toBe('1.50 s');
  });

  it('returns appropriate badge color classes based on score', () => {
    expect(getScoreTierBadgeColor(95).text).toBe('text-emerald-300');
    expect(getScoreTierBadgeColor(80).text).toBe('text-indigo-300');
    expect(getScoreTierBadgeColor(65).text).toBe('text-amber-300');
    expect(getScoreTierBadgeColor(45).text).toBe('text-rose-300');
  });

  it('summarizes search audit session with totals and averages', () => {
    const traces: SubQueryTrace[] = [
      {
        subQueryId: 't1',
        queryText: 'Transformer scaling law',
        category: 'academic',
        latencyMs: 350,
        payloadBytes: 15000,
        isFullText: true,
        hasAiRewrite: false,
        timestamp: Date.now(),
      },
      {
        subQueryId: 't2',
        queryText: 'PyTorch FSDP implementation',
        category: 'code',
        latencyMs: 420,
        payloadBytes: 25000,
        isFullText: true,
        hasAiRewrite: false,
        timestamp: Date.now(),
      },
    ];

    const citations: AuditCitationItem[] = [
      {
        id: 'c1',
        url: 'https://arxiv.org/abs/1706.03762',
        domain: 'arxiv.org',
        title: 'Attention Is All You Need',
        rawSnippet: 'We propose the Transformer...',
        subQueryId: 't1',
        qualityMatrix: calculateSourceQualityMatrix('https://arxiv.org/abs/1706.03762', true, false),
      },
    ];

    const session = summarizeSearchAuditSession('msg-123456', traces, citations);
    expect(session.totalLatencyMs).toBe(770);
    expect(session.totalPayloadBytes).toBe(40000);
    expect(session.averageQualityScore).toBeGreaterThanOrEqual(90);
    expect(session.traces).toHaveLength(2);
    expect(session.citations).toHaveLength(1);
  });
});
