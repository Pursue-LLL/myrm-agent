import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { HybridResourceLedgerCard } from '../HybridResourceLedgerCard';
import { BudgetQuotaIndicator } from '../BudgetQuotaIndicator';
import type { HybridLedgerReport } from '../types';

describe('HybridResourceLedgerCard & BudgetQuotaIndicator', () => {
  const mockNormalReport: HybridLedgerReport = {
    task_id: 'task-cloud-run-demo-01',
    hardware: {
      execution_seconds: 660.0,
      cpu_cores: 2.0,
      memory_gb: 4.0,
      volume_read_mb: 128.0,
      volume_write_mb: 64.0,
      hardware_credits: 11.46,
    },
    cognitive: {
      model_name: 'deepseek-v3',
      prompt_tokens: 25000,
      completion_tokens: 4500,
      cached_prompt_tokens: 15000,
      cognitive_credits: 113.5,
    },
    total_credits: 124.96,
    estimated_cost_usd: 1.2496,
    is_budget_exceeded: false,
    budget_exceeded_reason: '',
    created_at: 1700000000,
  };

  const mockExceededReport: HybridLedgerReport = {
    ...mockNormalReport,
    task_id: 'task-cloud-overtime-02',
    is_budget_exceeded: true,
    budget_exceeded_reason: '物理沙箱运行时间 (1200.0s) 超出最大预算配额 (600.0s)',
  };

  it('renders normal hybrid ledger report card with hardware and cognitive tracks', () => {
    render(<HybridResourceLedgerCard report={mockNormalReport} />);

    // 标题与任务 ID
    expect(screen.getByText(/混合算力对账单/i)).toBeInTheDocument();
    expect(screen.getByText(/AFP 协议/i)).toBeInTheDocument();
    expect(screen.getByText(/task-cloud-run-demo-01/i)).toBeInTheDocument();

    // 总积分与法币
    expect(screen.getByText('124.96')).toBeInTheDocument();
    expect(screen.getByText('1.2496')).toBeInTheDocument();

    // 硬件轨道
    expect(screen.getByText('11 分 0 秒')).toBeInTheDocument();
    expect(screen.getByText('2C / 4GB')).toBeInTheDocument();
    expect(screen.getByText(/读 128.0MB \/ 写 64.0MB/i)).toBeInTheDocument();
    expect(screen.getByText('11.46 Credits')).toBeInTheDocument();

    // 认知轨道
    expect(screen.getByText('deepseek-v3')).toBeInTheDocument();
    expect(screen.getByText('29,500')).toBeInTheDocument(); // 25000 + 4500
    expect(screen.getByText('113.50 Credits')).toBeInTheDocument();

    // 未超支时不展示熔断横幅
    expect(screen.queryByText(/预算熔断拦截/i)).toBeNull();
  });

  it('renders budget circuit breaker warning and quota indicators', () => {
    render(
      <HybridResourceLedgerCard
        report={mockExceededReport}
        maxSeconds={600}
        maxTokens={20000}
        maxCredits={100}
      />
    );

    // 熔断告警横幅
    expect(screen.getByText(/预算熔断拦截/i)).toBeInTheDocument();
    expect(screen.getByText(/物理沙箱运行时间 \(1200.0s\) 超出最大预算配额/i)).toBeInTheDocument();

    // 水位指示器渲染
    expect(screen.getByText(/任务多维预算配额水位/i)).toBeInTheDocument();
    expect(screen.getByText('物理沙箱时长')).toBeInTheDocument();
    expect(screen.getByText('认知 Token 消耗')).toBeInTheDocument();
    expect(screen.getAllByText('总算力积分消耗').length).toBeGreaterThanOrEqual(1);
  });

  it('renders BudgetQuotaIndicator independently with quota boundaries', () => {
    const { container, rerender } = render(<BudgetQuotaIndicator />);
    // 无任何配额时不渲染
    expect(container.firstChild).toBeNull();

    // 传入配额后正常渲染
    rerender(
      <BudgetQuotaIndicator
        currentSeconds={300}
        maxSeconds={600}
        currentTokens={10000}
        maxTokens={50000}
      />
    );

    expect(screen.getByText(/300 \/ 600 秒/i)).toBeInTheDocument();
    expect(screen.getByText(/10,000 \/ 50,000 Tokens/i)).toBeInTheDocument();
  });
});
