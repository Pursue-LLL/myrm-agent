import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SearchAuditEvidenceBadge } from '../SearchAuditEvidenceBadge';
import { useSearchAuditStore } from '../useSearchAuditStore';
import { SearchAuditSession, AuditCitationItem, SubQueryTrace } from '../searchAuditTypes';
import { calculateSourceQualityMatrix } from '../searchAuditEngine';

describe('SearchAuditEvidenceBadge', () => {
  const mockTrace: SubQueryTrace = {
    subQueryId: 'sq-1',
    queryText: 'SEC 10-K report NVIDIA',
    category: 'finance',
    latencyMs: 310,
    payloadBytes: 45000,
    isFullText: true,
    hasAiRewrite: false,
    timestamp: Date.now(),
  };

  const mockCitation: AuditCitationItem = {
    id: 'cite-nvda',
    url: 'https://www.sec.gov/edgar/data/1045810/nvda-10k.htm',
    domain: 'sec.gov',
    title: 'NVIDIA Corporation Form 10-K Annual Report',
    rawSnippet: 'Total revenue for fiscal year 2026 was $60.9 billion, up 126%...',
    subQueryId: 'sq-1',
    qualityMatrix: calculateSourceQualityMatrix('https://www.sec.gov/edgar/data/1045810/nvda-10k.htm', true, false),
  };

  const mockSession: SearchAuditSession = {
    auditSessionId: 'audit-sec-01',
    parentMessageId: 'msg-sec-01',
    totalLatencyMs: 310,
    totalPayloadBytes: 45000,
    averageQualityScore: 96,
    traces: [mockTrace],
    citations: [mockCitation],
    createdAt: Date.now(),
  };

  beforeEach(() => {
    useSearchAuditStore.getState().clearSession();
  });

  it('renders compact badge variant and opens drawer on click', () => {
    render(<SearchAuditEvidenceBadge session={mockSession} />);

    const compactBadge = screen.getByTestId('search-audit-evidence-badge-compact');
    expect(compactBadge).toBeInTheDocument();
    expect(screen.getByText('96分权威证据链')).toBeInTheDocument();
    expect(screen.getByText('310 ms')).toBeInTheDocument();

    fireEvent.click(compactBadge);
    expect(useSearchAuditStore.getState().isDrawerOpen).toBe(true);
    expect(useSearchAuditStore.getState().activeSession?.auditSessionId).toBe('audit-sec-01');
  });

  it('renders full badge card variant with trace and citation counts', () => {
    render(<SearchAuditEvidenceBadge session={mockSession} variant="full" />);

    const fullBadge = screen.getByTestId('search-audit-evidence-badge-full');
    expect(fullBadge).toBeInTheDocument();
    expect(screen.getByText('全透明检索证据链')).toBeInTheDocument();
    expect(screen.getByText('96分')).toBeInTheDocument();
    expect(screen.getByText(/1 次底层子查询 · 耗时 310 ms · 引用 1 处一手来源/)).toBeInTheDocument();
    expect(screen.getByText('展开审计')).toBeInTheDocument();

    fireEvent.click(fullBadge);
    expect(useSearchAuditStore.getState().isDrawerOpen).toBe(true);
  });

  it('passes initial citation target to store when clicked', () => {
    render(
      <SearchAuditEvidenceBadge
        session={mockSession}
        initialCitationId="cite-nvda"
      />
    );

    const badge = screen.getByTestId('search-audit-evidence-badge-compact');
    fireEvent.click(badge);

    expect(useSearchAuditStore.getState().isDrawerOpen).toBe(true);
    expect(useSearchAuditStore.getState().selectedCitation?.id).toBe('cite-nvda');
    expect(useSearchAuditStore.getState().activeTab).toBe('evidence_compare');
  });
});
