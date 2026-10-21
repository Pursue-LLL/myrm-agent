import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CausalTraceWaterfallView } from '../CausalTraceWaterfallView';
import { MultiTierHealthBadge } from '../MultiTierHealthBadge';
import type { CausalTraceData, MultiTierHealthReportData } from '../types';

describe('CausalTraceWaterfallView & MultiTierHealthBadge', () => {
  const mockTraceData: CausalTraceData = {
    trace_id: 'trace-abc-123456789',
    created_at: 1700000000,
    root: {
      name: 'agent_turn',
      kind: 'input',
      trace_id: 'trace-abc-123456789',
      span_id: 'span-root-1',
      start_time: 1700000000,
      end_time: 1700000000.5,
      duration_ms: 500.0,
      status: 'ok',
      attributes: {
        user_query: 'Search AI papers',
      },
      events: [],
      children: [
        {
          name: 'context_assemble',
          kind: 'context_stage',
          trace_id: 'trace-abc-123456789',
          span_id: 'span-ctx-2',
          parent_span_id: 'span-root-1',
          start_time: 1700000000,
          end_time: 1700000000.1,
          duration_ms: 100.0,
          status: 'ok',
          attributes: {
            retrieved_chunks: 5,
          },
          events: [],
          children: [],
        },
        {
          name: 'llm_reasoning',
          kind: 'llm_call',
          trace_id: 'trace-abc-123456789',
          span_id: 'span-llm-3',
          parent_span_id: 'span-root-1',
          start_time: 1700000000.1,
          end_time: 1700000000.4,
          duration_ms: 300.0,
          status: 'ok',
          attributes: {
            model: 'deepseek-r1',
            api_key: 'sk-***999',
          },
          events: [],
          children: [
            {
              name: 'web_search',
              kind: 'tool_call',
              trace_id: 'trace-abc-123456789',
              span_id: 'span-tool-4',
              parent_span_id: 'span-llm-3',
              start_time: 1700000000.2,
              end_time: 1700000000.35,
              duration_ms: 150.0,
              status: 'ok',
              attributes: {
                query: 'arXiv AI agent',
              },
              events: [],
              children: [],
            },
          ],
        },
      ],
    },
  };

  const mockHealthReport: MultiTierHealthReportData = {
    overall_status: 'healthy',
    summary: '所有组件与入口通道状态全绿，系统运行健康。',
    checked_at: 1700000000,
    probes: [
      {
        name: 'database',
        tier: 'component',
        status: 'healthy',
        latency_ms: 1.2,
        message: 'SQLite 正常',
        is_core: true,
        last_checked_at: 1700000000,
      },
      {
        name: 'webui_gateway',
        tier: 'ingress',
        status: 'healthy',
        latency_ms: 0.8,
        message: 'Gateway 监听中',
        is_core: true,
        last_checked_at: 1700000000,
      },
    ],
  };

  it('renders CausalTraceWaterfallView with span hierarchy and attributes toggle', () => {
    render(<CausalTraceWaterfallView trace={mockTraceData} />);

    expect(screen.getByTestId('causal-trace-waterfall-view')).toBeDefined();
    expect(screen.getByText(/单次任务因果时序链路/)).toBeDefined();
    expect(screen.getByText('agent_turn')).toBeDefined();
    expect(screen.getByText('context_assemble')).toBeDefined();
    expect(screen.getByText('llm_reasoning')).toBeDefined();
    expect(screen.getByText('web_search')).toBeDefined();

    // Verify stage labels
    expect(screen.getByText('用户输入')).toBeDefined();
    expect(screen.getByText('上下文装配')).toBeDefined();
    expect(screen.getByText('模型推理')).toBeDefined();
    expect(screen.getByText('工具执行')).toBeDefined();

    // Click llm_reasoning row to expand attributes
    const llmRow = screen.getByText('llm_reasoning');
    fireEvent.click(llmRow);

    // Verify redacted api_key attribute
    expect(screen.getByText('sk-***999')).toBeDefined();
    expect(screen.getByText('deepseek-r1')).toBeDefined();
  });

  it('renders MultiTierHealthBadge correctly with component and ingress tiers', () => {
    render(<MultiTierHealthBadge report={mockHealthReport} />);

    expect(screen.getByTestId('multi-tier-health-badge')).toBeDefined();
    expect(screen.getByText(/全层健康 \(HEALTHY\)/)).toBeDefined();
    expect(screen.getByText('组件支撑层 (Component Tier)')).toBeDefined();
    expect(screen.getByText('入口网关层 (Ingress Tier)')).toBeDefined();
    expect(screen.getByText('database')).toBeDefined();
    expect(screen.getByText('webui_gateway')).toBeDefined();
  });
});
