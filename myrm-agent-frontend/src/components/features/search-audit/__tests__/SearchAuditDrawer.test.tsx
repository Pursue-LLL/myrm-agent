import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SearchAuditDrawer } from '../SearchAuditDrawer';
import { useSearchAuditStore } from '../useSearchAuditStore';
import { SearchAuditSession, AuditCitationItem, SubQueryTrace } from '../searchAuditTypes';
import { calculateSourceQualityMatrix } from '../searchAuditEngine';

describe('SearchAuditDrawer', () => {
  const mockTrace: SubQueryTrace = {
    subQueryId: 'sq-101',
    queryText: 'flash attention 3 kernel optimization',
    category: 'code',
    latencyMs: 420,
    payloadBytes: 18432,
    isFullText: true,
    hasAiRewrite: false,
    timestamp: Date.now(),
  };

  const mockCitation: AuditCitationItem = {
    id: 'cite-202',
    url: 'https://github.com/Dao-AILab/flash-attention',
    domain: 'github.com',
    title: 'FlashAttention-3: Fast and Accurate Attention with Asynchrony',
    rawSnippet: 'FlashAttention-3 is designed for Hopper architecture with FP8 Tensor Cores...',
    fullTextSnippet: 'Benchmark results: 1.5x-2x speedup over FlashAttention-2 on H100 GPUs...',
    subQueryId: 'sq-101',
    qualityMatrix: calculateSourceQualityMatrix('https://github.com/Dao-AILab/flash-attention', true, false),
  };

  const mockSession: SearchAuditSession = {
    auditSessionId: 'audit-sess-555',
    parentMessageId: 'msg-777',
    totalLatencyMs: 420,
    totalPayloadBytes: 18432,
    averageQualityScore: 94,
    traces: [mockTrace],
    citations: [mockCitation],
    createdAt: Date.now(),
  };

  beforeEach(() => {
    useSearchAuditStore.getState().clearSession();
  });

  it('renders nothing when closed or no active session', () => {
    const { container } = render(<SearchAuditDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header, metrics ribbon and tabs when open', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession);
    render(<SearchAuditDrawer />);

    expect(screen.getByTestId('search-audit-drawer')).toBeInTheDocument();
    expect(screen.getByText('全透明检索链路审计')).toBeInTheDocument();
    expect(screen.getByText('94 分权威源')).toBeInTheDocument();
    expect(screen.getAllByText('420 ms').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('18.0 KB')).toBeInTheDocument();
    expect(screen.getByText('1 次 API 调用')).toBeInTheDocument();
  });

  it('closes drawer when clicking close button', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession);
    render(<SearchAuditDrawer />);

    const closeBtn = screen.getByRole('button', { name: '关闭检索审计抽屉' });
    fireEvent.click(closeBtn);
    expect(useSearchAuditStore.getState().isDrawerOpen).toBe(false);
  });

  it('displays sub-query traces in waterfall tab', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession);
    render(<SearchAuditDrawer />);

    expect(screen.getByText('flash attention 3 kernel optimization')).toBeInTheDocument();
    expect(screen.getByText('CODE')).toBeInTheDocument();
    expect(screen.getByText('一手原文拉取')).toBeInTheDocument();
    expect(screen.getByText('正文全文')).toBeInTheDocument();
  });

  it('switches to 100-score quality matrix tab and shows score breakdowns', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession);
    render(<SearchAuditDrawer />);

    const matrixTabBtn = screen.getByRole('button', { name: /100分质量矩阵/i });
    fireEvent.click(matrixTabBtn);

    expect(screen.getByText('FlashAttention-3: Fast and Accurate Attention with Asynchrony')).toBeInTheDocument();
    expect(screen.getByText(/权威度 \(40%\):/)).toBeInTheDocument();
    expect(screen.getByText(/一手性 \(20%\):/)).toBeInTheDocument();
    expect(screen.getByText(/信噪比 \(20%\):/)).toBeInTheDocument();
    expect(screen.getByText(/时效性 \(20%\):/)).toBeInTheDocument();
    expect(screen.getByText(/官方主分支\/标准规范 94分/)).toBeInTheDocument();
  });

  it('switches to evidence compare tab and renders raw and clean text snippets', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession, 'cite-202');
    render(<SearchAuditDrawer />);

    expect(
      screen.getByText('FlashAttention-3 is designed for Hopper architecture with FP8 Tensor Cores...')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Benchmark results: 1.5x-2x speedup over FlashAttention-2 on H100 GPUs.../)
    ).toBeInTheDocument();
  });
});
