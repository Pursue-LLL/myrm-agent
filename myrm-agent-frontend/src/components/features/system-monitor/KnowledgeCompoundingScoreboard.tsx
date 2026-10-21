/**
 * [INPUT]: KnowledgeCompoundingHealthSnapshot, onEvaluate or onRefresh handlers.
 * [OUTPUT]: KnowledgeCompoundingScoreboard component rendering 5-metric cards, overall index, and regression alerts.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/KnowledgeCompoundingScoreboard.tsx
 */

import React, { useState } from 'react';
import {
  CompoundingMetricPoint,
  CompoundingTier,
  EvaluateCompoundingPayload,
  KnowledgeCompoundingHealthSnapshot,
  MetricHealthStatus,
} from './knowledgeCompoundingTypes';

export interface KnowledgeCompoundingScoreboardProps {
  snapshot: KnowledgeCompoundingHealthSnapshot;
  onEvaluate?: (payload: EvaluateCompoundingPayload) => Promise<KnowledgeCompoundingHealthSnapshot>;
  onRefresh?: () => void;
}

export const KnowledgeCompoundingScoreboard: React.FC<KnowledgeCompoundingScoreboardProps> = ({
  snapshot,
  onEvaluate,
  onRefresh,
}) => {
  // 本地试算/模拟状态
  const [repErr, setRepErr] = useState<number>(
    snapshot.metrics['repeated_error_rate']?.value ?? 3.5
  );
  const [hitRate, setHitRate] = useState<number>(
    snapshot.metrics['knowledge_hit_rate']?.value ?? 68.0
  );
  const [corrections, setCorrections] = useState<number>(
    snapshot.metrics['human_corrections_count']?.value ?? 4
  );
  const [passRate, setPassRate] = useState<number>(
    snapshot.metrics['first_pass_success_rate']?.value ?? 88.5
  );
  const [staleRatio, setStaleRatio] = useState<number>(
    snapshot.metrics['stale_knowledge_ratio']?.value ?? 8.0
  );

  const [activeSnapshot, setActiveSnapshot] = useState<KnowledgeCompoundingHealthSnapshot>(snapshot);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);

  const getTierBadge = (tier: CompoundingTier) => {
    switch (tier) {
      case 'HIGHLY_COMPOUNDING':
        return {
          label: '★ HIGHLY COMPOUNDING (高度复利演进)',
          classes: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
        };
      case 'STEADY_GROWTH':
        return {
          label: '▲ STEADY GROWTH (稳步增长)',
          classes: 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30',
        };
      case 'EARLY_PHASE':
        return {
          label: '● EARLY PHASE (起步探索期)',
          classes: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
        };
      case 'REGRESSING':
      default:
        return {
          label: '🛑 REGRESSING (出现劣化或腐化)',
          classes: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
        };
    }
  };

  const getMetricStatusBadge = (status: MetricHealthStatus) => {
    switch (status) {
      case 'HEALTHY':
        return <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">健康达标</span>;
      case 'WARNING':
        return <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">轻度偏离</span>;
      case 'CRITICAL':
      default:
        return <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-400 border border-rose-500/30">严重劣化</span>;
    }
  };

  const handleRunEvaluation = async () => {
    const payload: EvaluateCompoundingPayload = {
      repeated_error_rate_pct: repErr,
      knowledge_hit_rate_pct: hitRate,
      human_corrections_count: corrections,
      first_pass_success_rate_pct: passRate,
      stale_knowledge_ratio_pct: staleRatio,
      window_days: activeSnapshot.window_days,
    };

    if (!onEvaluate) {
      // Local fallback calculation when remote evaluator not injected
      const isRegressing = repErr > 15 || hitRate < 30 || corrections > 15 || passRate < 60 || staleRatio > 25;
      const alerts: string[] = [];
      if (repErr > 15) alerts.push(`重复错误率偏高 (${repErr.toFixed(1)}%)，提示已知错误在后续任务中多次复现`);
      if (hitRate < 30) alerts.push(`跨会话知识命中率偏低 (${hitRate.toFixed(1)}%)，历史沉淀知识未充分参与决策`);
      if (corrections > 15) alerts.push(`人工纠正与打回重做频次过高 (${corrections} 次)`);
      if (passRate < 60) alerts.push(`任务一次通过率低于基线 (${passRate.toFixed(1)}%)`);
      if (staleRatio > 25) alerts.push(`过期与被忽视知识占比达到 ${staleRatio.toFixed(1)}%`);

      const calcScore = Math.max(
        0,
        Math.min(100, Math.round(passRate * 0.25 + hitRate * 0.25 + (20 - repErr) * 2 + (15 - Math.min(15, corrections)) * 2))
      );

      const localSnap: KnowledgeCompoundingHealthSnapshot = {
        overall_score: calcScore,
        compounding_tier: calcScore >= 85 ? 'HIGHLY_COMPOUNDING' : calcScore >= 70 ? 'STEADY_GROWTH' : calcScore >= 50 ? 'EARLY_PHASE' : 'REGRESSING',
        metrics: {
          repeated_error_rate: {
            name: 'repeated_error_rate',
            value: repErr,
            unit: '%',
            status: repErr <= 5 ? 'HEALTHY' : repErr <= 15 ? 'WARNING' : 'CRITICAL',
            benchmark_threshold: 5.0,
            description: '同类任务失败与死循环在后续执行中的复发比率',
            data_source_origin: 'loop_guard + failure_clustering',
          },
          knowledge_hit_rate: {
            name: 'knowledge_hit_rate',
            value: hitRate,
            unit: '%',
            status: hitRate >= 60 ? 'HEALTHY' : hitRate >= 40 ? 'WARNING' : 'CRITICAL',
            benchmark_threshold: 60.0,
            description: '跨会话任务决策中有效召回既往经验与沉淀记忆的占比',
            data_source_origin: 'memory.metrics::cross_session_hit_rate',
          },
          human_corrections_count: {
            name: 'human_corrections_count',
            value: corrections,
            unit: '次',
            status: corrections <= 5 ? 'HEALTHY' : corrections <= 15 ? 'WARNING' : 'CRITICAL',
            benchmark_threshold: 5.0,
            description: '周期内因产出质量不达标触发人工介入修改与纠偏的累计频次',
            data_source_origin: 'coordination_friction + memory.blind_spot',
          },
          first_pass_success_rate: {
            name: 'first_pass_success_rate',
            value: passRate,
            unit: '%',
            status: passRate >= 85 ? 'HEALTHY' : passRate >= 70 ? 'WARNING' : 'CRITICAL',
            benchmark_threshold: 85.0,
            description: '未经历多次返工重试即顺利通过验收的端到端任务占比',
            data_source_origin: 'eval.protocols::avg_pass_rate',
          },
          stale_knowledge_ratio: {
            name: 'stale_knowledge_ratio',
            value: staleRatio,
            unit: '%',
            status: staleRatio <= 10 ? 'HEALTHY' : staleRatio <= 25 ? 'WARNING' : 'CRITICAL',
            benchmark_threshold: 10.0,
            description: '长期未被引用、被覆写废弃或语义置信度严重衰减的记忆条目占比',
            data_source_origin: 'memory.health::detect_neglected',
          },
        },
        regression_alerts: alerts,
        evaluated_at: new Date().toISOString(),
        window_days: activeSnapshot.window_days,
      };

      setActiveSnapshot(localSnap);
      return;
    }

    try {
      setIsEvaluating(true);
      const res = await onEvaluate(payload);
      setActiveSnapshot(res);
    } finally {
      setIsEvaluating(false);
    }
  };

  const tierBadge = getTierBadge(activeSnapshot.compounding_tier);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 text-slate-100 shadow-xl space-y-6">
      {/* 顶部标题与进化指数总分 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-teal-500/10 text-teal-400 border border-teal-500/20 font-bold text-xs">
              KNOWLEDGE-COMPOUNDING
            </span>
            <h2 className="text-base font-semibold text-white">
              知识复利健康度全景记分板 (5-Metric Closure Scoreboard)
            </h2>
          </div>
          <p className="text-xs text-slate-400">
            拒绝盲盒假象：基于真实运行时数据闭环量化“智能体是否越用越聪明、经验是否有效沉淀”
          </p>
        </div>

        <div className="flex items-center gap-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md transition-colors"
            >
              刷新指标
            </button>
          )}
          <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700">
            <span className="text-xs text-slate-400">复利综合指数:</span>
            <span className="text-lg font-bold font-mono text-teal-300">
              {activeSnapshot.overall_score.toFixed(1)}
            </span>
            <span className="text-xs text-slate-500">/ 100</span>
          </div>
          <div className={`px-2.5 py-1 rounded-md text-xs font-semibold border ${tierBadge.classes}`}>
            {tierBadge.label}
          </div>
        </div>
      </div>

      {/* 劣化风险报警条幅 */}
      {activeSnapshot.regression_alerts.length > 0 && (
        <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-200 space-y-2">
          <div className="flex items-center gap-2 text-rose-400 font-semibold text-xs">
            <span>⚠️ 监测到 {activeSnapshot.regression_alerts.length} 项知识复利劣化预警 (Regression Alerts)</span>
          </div>
          <ul className="text-xs space-y-1 list-disc list-inside text-rose-300/90">
            {activeSnapshot.regression_alerts.map((alert, idx) => (
              <li key={idx}>{alert}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 五大核心指标卡片矩阵 */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        {Object.values(activeSnapshot.metrics).map((m: CompoundingMetricPoint) => (
          <div
            key={m.name}
            className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-700/60 flex flex-col justify-between space-y-2 hover:border-slate-600 transition-colors"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-300">{m.name}</span>
              {getMetricStatusBadge(m.status)}
            </div>

            <div>
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-bold font-mono text-white">
                  {m.value.toFixed(1)}
                </span>
                <span className="text-xs text-slate-400">{m.unit}</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                达标基线: {m.unit === '%' ? (m.name.includes('hit') || m.name.includes('pass') ? '≥ ' : '≤ ') : '≤ '}
                {m.benchmark_threshold}
                {m.unit}
              </div>
            </div>

            <div className="pt-2 border-t border-slate-800 text-[10px] text-slate-400 space-y-1">
              <p className="line-clamp-2 leading-tight">{m.description}</p>
              <div className="text-[9px] text-slate-500 font-mono">
                源: {m.data_source_origin}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 交互式模拟体检与微调器 */}
      <div className="p-4 rounded-lg bg-slate-800/30 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-slate-300">
            知识复利体检模拟微调器 (Interactive Simulator)
          </h3>
          <span className="text-[11px] text-slate-400">滑动调整参数进行情景演练</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4 text-xs">
          <div className="space-y-1">
            <div className="flex justify-between text-slate-400 text-[11px]">
              <span>重复错误率</span>
              <span className="font-mono text-slate-200">{repErr.toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="30"
              step="0.5"
              value={repErr}
              onChange={(e) => setRepErr(parseFloat(e.target.value))}
              className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-slate-400 text-[11px]">
              <span>知识命中率</span>
              <span className="font-mono text-slate-200">{hitRate.toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="1"
              value={hitRate}
              onChange={(e) => setHitRate(parseFloat(e.target.value))}
              className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-slate-400 text-[11px]">
              <span>人工纠正次数</span>
              <span className="font-mono text-slate-200">{corrections}次</span>
            </div>
            <input
              type="range"
              min="0"
              max="30"
              step="1"
              value={corrections}
              onChange={(e) => setCorrections(parseInt(e.target.value, 10))}
              className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-slate-400 text-[11px]">
              <span>一次通过率</span>
              <span className="font-mono text-slate-200">{passRate.toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min="30"
              max="100"
              step="1"
              value={passRate}
              onChange={(e) => setPassRate(parseFloat(e.target.value))}
              className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-slate-400 text-[11px]">
              <span>过期知识占比</span>
              <span className="font-mono text-slate-200">{staleRatio.toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="50"
              step="1"
              value={staleRatio}
              onChange={(e) => setStaleRatio(parseFloat(e.target.value))}
              className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={handleRunEvaluation}
            disabled={isEvaluating}
            className="px-4 py-1.5 bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-white rounded text-xs font-medium transition-colors"
          >
            {isEvaluating ? '正在评估...' : '执行情境体检试算'}
          </button>
        </div>
      </div>
    </div>
  );
};
