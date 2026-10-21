import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { KnowledgeCompoundingScoreboard } from '../KnowledgeCompoundingScoreboard';
import type {
  KnowledgeCompoundingHealthSnapshot,
} from '../knowledgeCompoundingTypes';

describe('KnowledgeCompoundingScoreboard', () => {
  const mockHealthySnapshot: KnowledgeCompoundingHealthSnapshot = {
    overall_score: 88.5,
    compounding_tier: 'HIGHLY_COMPOUNDING',
    metrics: {
      repeated_error_rate: {
        name: 'repeated_error_rate',
        value: 2.5,
        unit: '%',
        status: 'HEALTHY',
        benchmark_threshold: 5.0,
        description: '同类任务失败与死循环在后续执行中的复发比率',
        data_source_origin: 'loop_guard + failure_clustering',
      },
      knowledge_hit_rate: {
        name: 'knowledge_hit_rate',
        value: 75.0,
        unit: '%',
        status: 'HEALTHY',
        benchmark_threshold: 60.0,
        description: '跨会话任务决策中有效召回既往经验与沉淀记忆的占比',
        data_source_origin: 'memory.metrics::cross_session_hit_rate',
      },
      human_corrections_count: {
        name: 'human_corrections_count',
        value: 3,
        unit: '次',
        status: 'HEALTHY',
        benchmark_threshold: 5.0,
        description: '周期内因产出质量不达标触发人工介入修改与纠偏的累计频次',
        data_source_origin: 'coordination_friction + memory.blind_spot',
      },
      first_pass_success_rate: {
        name: 'first_pass_success_rate',
        value: 91.0,
        unit: '%',
        status: 'HEALTHY',
        benchmark_threshold: 85.0,
        description: '未经历多次返工重试即顺利通过验收的端到端任务占比',
        data_source_origin: 'eval.protocols::avg_pass_rate',
      },
      stale_knowledge_ratio: {
        name: 'stale_knowledge_ratio',
        value: 5.0,
        unit: '%',
        status: 'HEALTHY',
        benchmark_threshold: 10.0,
        description: '长期未被引用、被覆写废弃或语义置信度严重衰减的记忆条目占比',
        data_source_origin: 'memory.health::detect_neglected',
      },
    },
    regression_alerts: [],
    evaluated_at: '2026-10-12T00:00:00Z',
    window_days: 30,
  };

  const mockRegressingSnapshot: KnowledgeCompoundingHealthSnapshot = {
    overall_score: 42.0,
    compounding_tier: 'REGRESSING',
    metrics: {
      repeated_error_rate: {
        name: 'repeated_error_rate',
        value: 18.0,
        unit: '%',
        status: 'CRITICAL',
        benchmark_threshold: 5.0,
        description: '同类任务失败与死循环在后续执行中的复发比率',
        data_source_origin: 'loop_guard + failure_clustering',
      },
      knowledge_hit_rate: {
        name: 'knowledge_hit_rate',
        value: 20.0,
        unit: '%',
        status: 'CRITICAL',
        benchmark_threshold: 60.0,
        description: '跨会话任务决策中有效召回既往经验与沉淀记忆的占比',
        data_source_origin: 'memory.metrics::cross_session_hit_rate',
      },
      human_corrections_count: {
        name: 'human_corrections_count',
        value: 22,
        unit: '次',
        status: 'CRITICAL',
        benchmark_threshold: 5.0,
        description: '周期内因产出质量不达标触发人工介入修改与纠偏的累计频次',
        data_source_origin: 'coordination_friction',
      },
      first_pass_success_rate: {
        name: 'first_pass_success_rate',
        value: 48.0,
        unit: '%',
        status: 'CRITICAL',
        benchmark_threshold: 85.0,
        description: '未经历多次返工重试即顺利通过验收的端到端任务占比',
        data_source_origin: 'eval.protocols',
      },
      stale_knowledge_ratio: {
        name: 'stale_knowledge_ratio',
        value: 36.0,
        unit: '%',
        status: 'CRITICAL',
        benchmark_threshold: 10.0,
        description: '长期未被引用、被覆写废弃或语义置信度严重衰减的记忆条目占比',
        data_source_origin: 'memory.health',
      },
    },
    regression_alerts: [
      '重复错误率偏高 (18.0%)，提示已知错误在后续任务中多次复现',
      '过期与被忽视知识占比达到 36.0%，知识库存在腐化风险',
    ],
    evaluated_at: '2026-10-12T00:00:00Z',
    window_days: 14,
  };

  it('renders healthy compounding scoreboard and all 5 metrics', () => {
    const handleRefresh = vi.fn();
    render(
      <KnowledgeCompoundingScoreboard
        snapshot={mockHealthySnapshot}
        onRefresh={handleRefresh}
      />
    );

    // Title & Score
    expect(
      screen.getByText('知识复利健康度全景记分板 (5-Metric Closure Scoreboard)')
    ).toBeInTheDocument();
    expect(screen.getByText('88.5')).toBeInTheDocument();
    expect(screen.getByText('★ HIGHLY COMPOUNDING (高度复利演进)')).toBeInTheDocument();

    // 5 Metric Names
    expect(screen.getByText('repeated_error_rate')).toBeInTheDocument();
    expect(screen.getByText('knowledge_hit_rate')).toBeInTheDocument();
    expect(screen.getByText('human_corrections_count')).toBeInTheDocument();
    expect(screen.getByText('first_pass_success_rate')).toBeInTheDocument();
    expect(screen.getByText('stale_knowledge_ratio')).toBeInTheDocument();

    // Health Badges
    expect(screen.getAllByText('健康达标').length).toBe(5);

    // Refresh action
    fireEvent.click(screen.getByText('刷新指标'));
    expect(handleRefresh).toHaveBeenCalledTimes(1);
  });

  it('renders regression warning banner and regressing tier for degraded memory health', () => {
    render(
      <KnowledgeCompoundingScoreboard
        snapshot={mockRegressingSnapshot}
      />
    );

    expect(screen.getByText('🛑 REGRESSING (出现劣化或腐化)')).toBeInTheDocument();
    expect(
      screen.getByText(/监测到 2 项知识复利劣化预警/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/重复错误率偏高 \(18.0%\)/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/过期与被忽视知识占比达到 36.0%/)
    ).toBeInTheDocument();
    expect(screen.getAllByText('严重劣化').length).toBe(5);
  });

  it('triggers interactive simulation evaluation on button click', async () => {
    const mockEvaluate = vi.fn().mockResolvedValue({
      ...mockHealthySnapshot,
      overall_score: 93.0,
    });

    render(
      <KnowledgeCompoundingScoreboard
        snapshot={mockHealthySnapshot}
        onEvaluate={mockEvaluate}
      />
    );

    const evalBtn = screen.getByText('执行情境体检试算');
    fireEvent.click(evalBtn);

    await waitFor(() => {
      expect(mockEvaluate).toHaveBeenCalledTimes(1);
      expect(screen.getByText('93.0')).toBeInTheDocument();
    });
  });
});
