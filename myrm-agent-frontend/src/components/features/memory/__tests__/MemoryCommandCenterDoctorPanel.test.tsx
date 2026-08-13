/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ./MemoryCommandCenterDoctorPanel::MemoryDoctorPanel (POS: 记忆 Doctor 面板，含诊断趋势)
 *
 * [OUTPUT]
 * MemoryDoctorPanel diagnostic trend tests: latency p50/p95 ms 分支、delta 颜色语义、
 * MiniTrendBar title、类别通过率、run 状态徽章与 embedding 模型漂移提示。
 *
 * [POS]
 * 记忆 Doctor 面板趋势区渲染回归测试。验证 latency 性能趋势（唯一性能退化告警维度）正确渲染。
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type {
  MemoryCommandCenterResponse,
  MemoryCommandDiagnosticHistoryItem,
} from '@/services/memoryCommandCenter';
import { MemoryDoctorPanel } from '../command-center/MemoryCommandCenterDoctorPanel';
import type { DoctorExecutableAction } from '../command-center/MemoryCommandCenterDoctorPanel';

type MemoryTranslation = ReturnType<typeof import('next-intl').useTranslations<'memory'>>;

const t = ((key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join(',')}` : key) as unknown as MemoryTranslation;

const makeBenchmark = (overrides: Partial<Record<string, number | Record<string, string>>> = {}) => ({
  case_count: 16,
  passed_count: 14,
  recall_at_k: 0.8,
  ndcg_at_k: 0.85,
  mrr_score: 0.7,
  precision_at_k: 0.9,
  latency_p50_ms: 150,
  latency_p95_ms: 220,
  top_k: 5,
  categories: { profile: '2/2', workflow_event: '1/2' },
  ...overrides,
});

const makeHistoryItem = (
  runId: string,
  overrides: Partial<MemoryCommandDiagnosticHistoryItem> = {},
): MemoryCommandDiagnosticHistoryItem =>
  ({
    run_id: runId,
    status: 'ready',
    occurred_at: '2026-08-10T08:00:00Z',
    duration_ms: 12000,
    probe_count: 14,
    failed_count: 0,
    benchmark: makeBenchmark(),
    embedding_model: 'BAAI/bge-m3',
    ...overrides,
  }) as MemoryCommandDiagnosticHistoryItem;

const makeSnapshot = (): MemoryCommandCenterResponse =>
  ({ doctor_checks: [] }) as unknown as MemoryCommandCenterResponse;

describe('MemoryDoctorPanel diagnostic trend', () => {
  it('renders latency p50/p95 in ms with green/red delta semantics and model-shift hint', () => {
    // history follows the API contract: newest first.
    const history = [
      makeHistoryItem('run-2', {
        occurred_at: '2026-08-10T08:00:00Z',
        status: 'warning',
        embedding_model: 'text-embedding-v3',
        benchmark: makeBenchmark({
          recall_at_k: 0.9,
          ndcg_at_k: 0.8,
          latency_p50_ms: 150,
          latency_p95_ms: 250,
        }),
      }),
      makeHistoryItem('run-1', {
        occurred_at: '2026-08-09T08:00:00Z',
        benchmark: makeBenchmark({ recall_at_k: 0.8, latency_p50_ms: 120, latency_p95_ms: 210 }),
      }),
    ];

    const { container } = render(
      <MemoryDoctorPanel
        snapshot={makeSnapshot()}
        t={t}
        actionId={null}
        diagnosticRun={null}
        diagnosticHistory={history}
        onDoctorAction={(_action: DoctorExecutableAction) => {}}
      />,
    );

    expect(screen.getByText('commandCenter.doctorTrendTitle')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.doctorTrendRuns:2')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.readinessStatus.warning')).toBeInTheDocument();

    expect(screen.getByText('commandCenter.benchmarkRecall:5')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.benchmarkLatencyP50')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.benchmarkLatencyP95')).toBeInTheDocument();

    // recall 上升 +10% → emerald
    expect(screen.getByText('+10%').className).toContain('text-emerald-500');
    // latency p50 上升 +30ms → red（性能退化告警）
    expect(screen.getByText('+30ms').className).toContain('text-red-500');
    // latency p95 上升 +40ms → red
    expect(screen.getByText('+40ms').className).toContain('text-red-500');
    // ndcg 下降 -5% → red
    expect(screen.getByText('-5%').className).toContain('text-red-500');

    // 最新 latency 值与 MiniTrendBar title 均为 ms 格式
    expect(screen.getByText('150ms')).toBeInTheDocument();
    expect(container.querySelector('[title="150ms"]')).not.toBeNull();
    expect(container.querySelector('[title="120ms"]')).not.toBeNull();
    expect(container.querySelector('[title="250ms"]')).not.toBeNull();

    // 类别通过率（非全过 → amber）
    expect(screen.getByText('workflow event 1/2').className).toContain('text-amber-600');

    // embedding 模型漂移提示
    expect(screen.getByText(/commandCenter\.doctorTrendModelShift/)).toBeInTheDocument();
  });

  it('shows emerald when latency drops and omits model-shift when models match', () => {
    const history = [
      makeHistoryItem('run-2', {
        occurred_at: '2026-08-10T08:00:00Z',
        benchmark: makeBenchmark({ latency_p50_ms: 120 }),
      }),
      makeHistoryItem('run-1', {
        occurred_at: '2026-08-09T08:00:00Z',
        benchmark: makeBenchmark({ latency_p50_ms: 150 }),
      }),
    ];

    render(
      <MemoryDoctorPanel
        snapshot={makeSnapshot()}
        t={t}
        actionId={null}
        diagnosticRun={null}
        diagnosticHistory={history}
        onDoctorAction={(_action: DoctorExecutableAction) => {}}
      />,
    );

    // latency 下降 -30ms → emerald
    expect(screen.getByText('-30ms').className).toContain('text-emerald-500');
    expect(screen.queryByText('commandCenter.doctorTrendModelShift')).toBeNull();
  });

  it('hides trend section when fewer than two benchmarked runs exist', () => {
    const { rerender } = render(
      <MemoryDoctorPanel
        snapshot={makeSnapshot()}
        t={t}
        actionId={null}
        diagnosticRun={null}
        diagnosticHistory={[]}
        onDoctorAction={(_action: DoctorExecutableAction) => {}}
      />,
    );
    expect(screen.queryByText('commandCenter.doctorTrendTitle')).toBeNull();

    rerender(
      <MemoryDoctorPanel
        snapshot={makeSnapshot()}
        t={t}
        actionId={null}
        diagnosticRun={null}
        diagnosticHistory={[makeHistoryItem('run-1')]}
        onDoctorAction={(_action: DoctorExecutableAction) => {}}
      />,
    );
    expect(screen.queryByText('commandCenter.doctorTrendTitle')).toBeNull();
  });

  it('skips history items without a benchmark when computing trends', () => {
    const history = [
      makeHistoryItem('run-3', {
        occurred_at: '2026-08-10T08:00:00Z',
        benchmark: makeBenchmark({ latency_p50_ms: 90 }),
      }),
      makeHistoryItem('run-2', { occurred_at: '2026-08-09T20:00:00Z', benchmark: null }),
      makeHistoryItem('run-1', {
        occurred_at: '2026-08-09T08:00:00Z',
        benchmark: makeBenchmark({ latency_p50_ms: 100 }),
      }),
    ];

    render(
      <MemoryDoctorPanel
        snapshot={makeSnapshot()}
        t={t}
        actionId={null}
        diagnosticRun={null}
        diagnosticHistory={history}
        onDoctorAction={(_action: DoctorExecutableAction) => {}}
      />,
    );

    expect(screen.getByText('commandCenter.doctorTrendTitle')).toBeInTheDocument();
    expect(screen.getByText('-10ms').className).toContain('text-emerald-500');
  });
});
