import React, { useState } from 'react';
import { ElasticThrottlingCardView } from './graph-triage/ElasticThrottlingCardView';
import { PredictiveBudgetGaugeView } from './graph-triage/PredictiveBudgetGaugeView';
import { TriageDecisionBannerView } from './graph-triage/TriageDecisionBannerView';
import {
  type BudgetEstimate,
  type BudgetStatusType,
  type ExecutionSpendState,
  INITIAL_MOCK_DECISION,
  INITIAL_MOCK_ESTIMATE,
  INITIAL_MOCK_SPEND,
  type PartialReduceReport,
  type TriageDecision,
} from './graph-triage/types';

export const GraphApplicabilityTriageCard: React.FC = () => {
  const [decision, setDecision] = useState<TriageDecision>(INITIAL_MOCK_DECISION);
  const [estimate, setEstimate] = useState<BudgetEstimate>(INITIAL_MOCK_ESTIMATE);
  const [spendState, setSpendState] = useState<ExecutionSpendState>(INITIAL_MOCK_SPEND);
  const [nodeCount, setNodeCount] = useState<number>(4);
  const [fanoutConcurrency, setFanoutConcurrency] = useState<number>(4);
  const [reduceReport, setReduceReport] = useState<PartialReduceReport | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>('图工程自适应准入门禁与预算熔断防护网已就绪。');

  // Handle Scenario Triage Switching
  const handleSelectScenario = (scenario: 'simple' | 'exploratory' | 'sequential' | 'parallel') => {
    if (scenario === 'simple') {
      setDecision({
        verdict: 'reject_to_single_agent',
        category: 'simple_single_step',
        reason: '任务属于单步操作（如错别字修复），图多智能体编排会导致严重响应延迟与数十倍 Token 浪费，强制降级为单 Agent 执行。',
        recommended_mode: 'Single-Agent Direct Execution',
        estimated_speedup_ratio: 5.0,
        estimated_tokens_saved: 45000,
        features: {
          prompt_length: 12,
          declared_subtasks_count: 1,
          independent_parallel_count: 1,
          max_dependency_depth: 1,
          is_conversational_inquiry: false,
          has_isolated_heavyweight_steps: false,
        },
      });
      setStatusMessage('已拦截伪需求：单步小任务强制降级为单 Agent 执行，预估节省 45,000 Tokens。');
    } else if (scenario === 'exploratory') {
      setDecision({
        verdict: 'reject_to_conversational',
        category: 'exploratory_chat',
        reason: '任务属于未定型探索性头脑风暴或人机互动对话，盲目拉起图编排会破坏交互上下文连贯性，保持单 Agent 交互模式。',
        recommended_mode: 'Conversational Interactive Session',
        estimated_speedup_ratio: 3.5,
        estimated_tokens_saved: 30000,
        features: {
          prompt_length: 56,
          declared_subtasks_count: 1,
          independent_parallel_count: 1,
          max_dependency_depth: 1,
          is_conversational_inquiry: true,
          has_isolated_heavyweight_steps: false,
        },
      });
      setStatusMessage('已拦截探索对话：保持交互式对话模式，防止多智能体分裂碎片化。');
    } else if (scenario === 'sequential') {
      setDecision({
        verdict: 'reject_to_linear_pipeline',
        category: 'strictly_sequential',
        reason: '所有子任务具备强因果时序依赖链条，不存在独立可并行扇出分支，图编排只会引入拓扑空转开销，保持轻量线性流水线模式。',
        recommended_mode: 'Linear Sequential Pipeline',
        estimated_speedup_ratio: 2.0,
        estimated_tokens_saved: 20000,
        features: {
          prompt_length: 80,
          declared_subtasks_count: 4,
          independent_parallel_count: 1,
          max_dependency_depth: 4,
          is_conversational_inquiry: false,
          has_isolated_heavyweight_steps: false,
        },
      });
      setStatusMessage('已拦截纯时序依赖：保持轻量单向流水线，规避复杂图开销。');
    } else {
      setDecision(INITIAL_MOCK_DECISION);
      setStatusMessage('准入多智能体图工程：检测到 3 个真正独立重型并行分支，启动图编排加速。');
    }
  };

  // Handle Predictive Budget Updates
  const handleUpdateBudgetParams = (nodes: number, concurrency: number) => {
    setNodeCount(nodes);
    setFanoutConcurrency(concurrency);
    const predictedTokens = 1000 + nodes * 12000 + concurrency * 1500;
    const predictedCost = Number(((predictedTokens / 1000) * 0.003).toFixed(4));
    const isBroken = predictedTokens > estimate.max_tokens_cap || predictedCost > estimate.max_cost_usd_cap;

    setEstimate((prev) => ({
      ...prev,
      total_estimated_tokens: predictedTokens,
      estimated_cost_usd: predictedCost,
      is_circuit_broken: isBroken,
      recommendation: isBroken
        ? `INTERCEPT: 预估 ${predictedTokens.toLocaleString()} Tokens ($${predictedCost}) 超出设定硬上限！`
        : 'ALLOW: 预估资源消耗在安全硬上限阈值内。',
    }));
  };

  // Simulate Massive Over-Cap Fanout
  const handleSimulateMassiveFanout = () => {
    setNodeCount(16);
    setFanoutConcurrency(8);
    const predictedTokens = 205000;
    const predictedCost = 0.615;
    setEstimate((prev) => ({
      ...prev,
      total_estimated_tokens: predictedTokens,
      estimated_cost_usd: predictedCost,
      is_circuit_broken: true,
      recommendation: `INTERCEPT: 预估 ${predictedTokens.toLocaleString()} Tokens 超出 100,000 硬上限，熔断门禁已阻断扇出！`,
    }));
    setStatusMessage('警报：模拟 16 节点重型扇出超出硬上限，图工程熔断门禁成功拦截！');
  };

  // Simulate Runtime Dynamic Spend Step
  const handleSimulateSpendStep = (target: BudgetStatusType) => {
    const maxTokens = 100000;
    if (target === 'healthy') {
      const current = 20000;
      setSpendState({
        session_id: 'graph-triage-demo-session',
        current_tokens: current,
        current_cost_usd: 0.06,
        remaining_tokens: maxTokens - current,
        remaining_budget_pct: 0.8,
        budget_status: 'healthy',
        active_concurrency: 4,
        is_throttled: false,
        is_circuit_broken: false,
      });
      setStatusMessage('预算水位充裕（80%），维持全量 4 路并发执行。');
    } else if (target === 'warning') {
      const current = 75000;
      setSpendState({
        session_id: 'graph-triage-demo-session',
        current_tokens: current,
        current_cost_usd: 0.225,
        remaining_tokens: maxTokens - current,
        remaining_budget_pct: 0.25,
        budget_status: 'warning',
        active_concurrency: 2,
        is_throttled: true,
        is_circuit_broken: false,
      });
      setStatusMessage('预算进入预警区间（25% <= 30%），并发度自适应降级至 2 路。');
    } else if (target === 'critical') {
      const current = 92000;
      setSpendState({
        session_id: 'graph-triage-demo-session',
        current_tokens: current,
        current_cost_usd: 0.276,
        remaining_tokens: maxTokens - current,
        remaining_budget_pct: 0.08,
        budget_status: 'critical',
        active_concurrency: 1,
        is_throttled: true,
        is_circuit_broken: false,
      });
      setStatusMessage('预算进入危急区间（8% <= 10%），降为单并发并建议触发提前局部归约！');
    } else {
      const current = 100000;
      setSpendState({
        session_id: 'graph-triage-demo-session',
        current_tokens: current,
        current_cost_usd: 0.3,
        remaining_tokens: 0,
        remaining_budget_pct: 0.0,
        budget_status: 'exhausted',
        active_concurrency: 0,
        is_throttled: true,
        is_circuit_broken: true,
      });
      setStatusMessage('额度已耗尽，熔断器强行切断派发并发度归零，保护账户资金。');
    }
  };

  // Trigger Graceful Early Reduce
  const handleTriggerEarlyReduce = () => {
    const report: PartialReduceReport = {
      session_id: spendState.session_id,
      summary:
        'Graceful Early Reduce Triggered (CRITICAL).\n' +
        '[auth_scanner]: 完成 14 个鉴权路由与 JWT 漏洞扫描，未发现未授权越权风险。\n' +
        '[db_auditor]: 完成 SQL 迁移文件审计，发现 2 处未建索引外键。\n' +
        '已跳过后续 2 个待执行节点，保全成果成功交付。',
      completed_nodes: ['auth_scanner', 'db_auditor'],
      unexecuted_nodes: ['stress_tester', 'compliance_checker'],
      tokens_spent: spendState.current_tokens,
      tokens_saved: Math.max(0, 100000 - spendState.current_tokens),
      delivery_confidence: 0.5,
      reason: '剩余预算低于10%阈值，自动启动提前局部优雅归约，杜绝算力耗尽导致的成果全盘清零。',
    };
    setReduceReport(report);
    setStatusMessage('提前局部归约执行完成：已保全交付 2 个核心节点产物，节省 8,000+ Tokens。');
  };

  return (
    <article
      data-testid="graph-applicability-triage-card"
      aria-label="图工程自适应适用性评估门禁与并发 Token 预算熔断套件"
      className="my-3 flex flex-col gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-950 sm:p-5"
    >
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 pb-3 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-base dark:bg-indigo-950/60">
            📊
          </span>
          <div>
            <h2 className="text-sm font-bold text-gray-900 dark:text-gray-100">
              GraphApplicabilityTriageGateAndElasticBudgetCircuitBreakerPack
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              图工程自适应适用性评估门禁 · 前置 Token 预估 · 自适应并发节流与提前局部优雅归约
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
            P0 核心经济性治理
          </span>
        </div>
      </header>

      {/* 1. Triage Decision Banner */}
      <TriageDecisionBannerView decision={decision} onSelectScenario={handleSelectScenario} />

      {/* 2. Predictive Budget Gauge */}
      <PredictiveBudgetGaugeView
        estimate={estimate}
        nodeCount={nodeCount}
        fanoutConcurrency={fanoutConcurrency}
        onUpdateParams={handleUpdateBudgetParams}
        onSimulateMassiveFanout={handleSimulateMassiveFanout}
      />

      {/* 3. Elastic Throttling & Early Reduce Card */}
      <ElasticThrottlingCardView
        spendState={spendState}
        reduceReport={reduceReport}
        onSimulateStep={handleSimulateSpendStep}
        onTriggerEarlyReduce={handleTriggerEarlyReduce}
      />

      {/* Live Accessibility Feedback */}
      <footer className="border-t border-gray-100 pt-3 dark:border-gray-800">
        <output
          data-testid="graph-triage-status-live"
          aria-live="polite"
          className="block text-xs font-medium text-gray-600 dark:text-gray-300"
        >
          {statusMessage}
        </output>
      </footer>
    </article>
  );
};
