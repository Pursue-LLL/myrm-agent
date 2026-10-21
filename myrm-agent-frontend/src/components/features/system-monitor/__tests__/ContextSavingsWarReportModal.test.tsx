import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ContextSavingsWarReportModal } from '../ContextSavingsWarReportModal';
import { EngineeringInsightRoleDeck } from '../EngineeringInsightRoleDeck';
import type {
  RoleEngineeringInsightReport,
  SessionSavingsAudit,
} from '../contextSavingsTypes';

describe('ContextSavingsWarReportModal & EngineeringInsightRoleDeck', () => {
  const mockAudit: SessionSavingsAudit = {
    session_id: 'sess-crawl-test-01',
    total_tool_calls: 3,
    total_original_tokens: 140000,
    total_optimized_tokens: 7000,
    total_saved_tokens: 133000,
    overall_savings_rate_pct: 95.0,
    total_cost_saved_usd: 0.399,
    total_cost_saved_cny: 2.8529,
    summary_headline: '🎉 本次会话通过智能上下文拦截为您节省了 133,000 Tokens，整体节省率 95.0%，折合节省约 ¥2.85 / $0.40',
    tool_breakdown: [
      {
        tool_name: 'playwright_browser_scrape',
        total_calls: 1,
        total_original_tokens: 100000,
        total_optimized_tokens: 2000,
        total_saved_tokens: 98000,
        average_savings_rate_pct: 98.0,
        total_cost_saved_usd: 0.294,
        total_cost_saved_cny: 2.1021,
        cache_hit_rate_pct: 0.0,
      },
      {
        tool_name: 'bash_build_run',
        total_calls: 2,
        total_original_tokens: 40000,
        total_optimized_tokens: 5000,
        total_saved_tokens: 35000,
        average_savings_rate_pct: 87.5,
        total_cost_saved_usd: 0.105,
        total_cost_saved_cny: 0.7508,
        cache_hit_rate_pct: 50.0,
      },
    ],
  };

  const mockReport: RoleEngineeringInsightReport = {
    role: 'CTO',
    evaluated_sessions_count: 5,
    total_saved_tokens_aggregate: 520000,
    total_cost_saved_usd_aggregate: 1.56,
    top_efficiency_tools: ['playwright_browser_scrape', 'bash_build_run'],
    primary_bottleneck_summary: 'CTO 视窗: 累计节省 520,000 Tokens，重点防范输出膨胀与死锁瓶颈。',
    identified_engineering_signals: [
      {
        signal_pattern: 'TOOL_OUTPUT_BLOAT',
        severity: 'HIGH',
        target_entity: 'playwright_browser_scrape',
        detected_metric_value: 100000,
        metric_threshold: 15000,
        root_cause_explanation: '工具原始输出达 100,000 tokens，极度依赖上下文拦截。',
        actionable_remediation: '配置按需分页或在入参层主动约束行数。',
      },
      {
        signal_pattern: 'HIGH_RETRY_CHURN',
        severity: 'MEDIUM',
        target_entity: 'bash_build_run',
        detected_metric_value: 3,
        metric_threshold: 3,
        root_cause_explanation: '检测到连续 3 次重试执行。',
        actionable_remediation: '检查环境稳定性并在第 2 次失败后主动介入。',
      },
    ],
  };

  it('renders war report modal with headline, key KPIs, and tool breakdown table', () => {
    const onClose = vi.fn();
    const onExport = vi.fn();

    render(
      <ContextSavingsWarReportModal
        isOpen={true}
        audit={mockAudit}
        onClose={onClose}
        onExportJson={onExport}
      />
    );

    // Title & Session
    expect(screen.getByText('上下文拦截节流战报')).toBeInTheDocument();
    expect(screen.getByText(/会话: sess-crawl-test-01/)).toBeInTheDocument();

    // Headline
    expect(screen.getByText(/本次会话通过智能上下文拦截为您节省了 133,000 Tokens/)).toBeInTheDocument();

    // KPI values
    expect(screen.getByText('133,000')).toBeInTheDocument();
    expect(screen.getByText('95%')).toBeInTheDocument();
    expect(screen.getByText('¥2.85')).toBeInTheDocument();

    // Tool breakdown
    expect(screen.getByText('playwright_browser_scrape')).toBeInTheDocument();
    expect(screen.getByText('bash_build_run')).toBeInTheDocument();
    expect(screen.getByText('98%')).toBeInTheDocument();

    // Export button click
    const exportBtn = screen.getByRole('button', { name: /导出 .savings.json/ });
    fireEvent.click(exportBtn);
    expect(onExport).toHaveBeenCalledTimes(1);

    // Close button click
    const closeBtn = screen.getByRole('button', { name: '关闭战报' });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders engineering insight role deck and handles role switching and scan triggers', () => {
    const onRoleChange = vi.fn();
    const onTriggerScan = vi.fn();

    render(
      <EngineeringInsightRoleDeck
        report={mockReport}
        selectedRole="CTO"
        onRoleChange={onRoleChange}
        onTriggerSessionScan={onTriggerScan}
      />
    );

    // Title
    expect(screen.getByText('跨工具 Token 节省率与工程信号七维决策看板')).toBeInTheDocument();
    expect(screen.getByText(/CTO 视窗: 累计节省 520,000 Tokens/)).toBeInTheDocument();

    // Role tabs
    const finopsBtn = screen.getByRole('button', { name: 'FINOPS' });
    fireEvent.click(finopsBtn);
    expect(onRoleChange).toHaveBeenCalledWith('FINOPS');

    // Aggregate stats
    expect(screen.getByText('520,000')).toBeInTheDocument();
    expect(screen.getByText('$1.56')).toBeInTheDocument();

    // Signals
    expect(screen.getByText('TOOL_OUTPUT_BLOAT')).toBeInTheDocument();
    expect(screen.getByText('HIGH_RETRY_CHURN')).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();
    expect(screen.getByText('MEDIUM')).toBeInTheDocument();

    // Trigger scan
    const scanBtn = screen.getByRole('button', { name: /重新扫描信号/ });
    fireEvent.click(scanBtn);
    expect(onTriggerScan).toHaveBeenCalledTimes(1);
  });
});
