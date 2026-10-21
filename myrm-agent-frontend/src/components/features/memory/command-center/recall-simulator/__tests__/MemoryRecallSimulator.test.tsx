/** @vitest-environment jsdom */

import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRecallSimulator } from '../MemoryRecallSimulator';
import { RecallSimulatorService } from '../recallSimulatorService';
import { RecallSimulateResponse } from '../recallSimulatorTypes';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    drawerTitle: '记忆与经验召回模拟沙盒',
    drawerSubtitle: '对标 EvoX 召回测试与治理中心',
    queryInputPlaceholder: '输入测试提示词或任务指令...',
    simulateBtn: '模拟召回',
    simulatingBtn: '检索中...',
    totalMatched: '命中记忆数',
    latency: '检索延迟',
    rrfScore: 'RRF 融合分',
    bm25Score: 'BM25 词法',
    vectorSim: '向量语义',
    causalAffinity: '因果基因',
    confidenceWeight: '置信度权重',
    mustAvoidTrap: '强负向避坑基因',
    normalGene: '普通正向经验',
    emptyResults: '未检索到匹配的记忆或经验基因',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockSimResponse: RecallSimulateResponse = {
  query: 'Linux 内核死锁',
  total_matched: 1,
  candidates: [
    {
      memory_id: 'mem-linux-deadlock-01',
      content: 'Linux 中断上下文严禁调用 mutex_lock',
      summary: '中断上下文自旋锁避坑',
      recall_type: 'causal_gene',
      scores: {
        rrf_score: 0.94,
        bm25_score: 12.8,
        vector_similarity: 0.88,
        causal_relevance: 0.96,
      },
      confidence: 0.95,
      is_negative_trap: true,
      status: 'active',
      hit_reason: '命中因果避坑基因',
      tags: ['Linux', 'Kernel'],
    },
  ],
  execution_latency_ms: 10.2,
};

describe('MemoryRecallSimulator', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(<MemoryRecallSimulator isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders simulator drawer with title and initial query', () => {
    render(<MemoryRecallSimulator isOpen={true} onClose={vi.fn()} initialQuery="排查并发死锁" />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('记忆与经验召回模拟沙盒')).toBeInTheDocument();
    expect(screen.getByDisplayValue('排查并发死锁')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /模拟召回/i })).toBeInTheDocument();
  });

  it('triggers recall simulation and displays candidates and metrics', async () => {
    const simulateSpy = vi.spyOn(RecallSimulatorService, 'simulateRecall').mockResolvedValueOnce(mockSimResponse);

    render(<MemoryRecallSimulator isOpen={true} onClose={vi.fn()} initialQuery="Linux 内核死锁" />);

    const simulateBtn = screen.getByRole('button', { name: /模拟召回/i });
    await act(async () => {
      fireEvent.click(simulateBtn);
    });

    expect(simulateSpy).toHaveBeenCalledWith({
      query: 'Linux 内核死锁',
      top_k: 5,
      domain_filter: null,
      recall_types: ['bm25', 'vector', 'causal_gene'],
    });

    expect(screen.getByText('mem-linux-deadlock-01')).toBeInTheDocument();
    expect(screen.getByText('中断上下文自旋锁避坑')).toBeInTheDocument();
    expect(screen.getByText('94.0%')).toBeInTheDocument();
    expect(screen.getByText('10.2 ms')).toBeInTheDocument();
  });

  it('renders empty result message when response has zero candidates', async () => {
    vi.spyOn(RecallSimulatorService, 'simulateRecall').mockResolvedValueOnce({
      query: 'unknown topic',
      total_matched: 0,
      candidates: [],
      execution_latency_ms: 5.0,
    });

    render(<MemoryRecallSimulator isOpen={true} onClose={vi.fn()} initialQuery="unknown topic" />);

    const simulateBtn = screen.getByRole('button', { name: /模拟召回/i });
    await act(async () => {
      fireEvent.click(simulateBtn);
    });

    expect(screen.getByText('未检索到匹配的记忆或经验基因')).toBeInTheDocument();
  });

  it('invokes onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(<MemoryRecallSimulator isOpen={true} onClose={handleClose} />);

    const closeBtn = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
