/**
 * FinancialSandplayWidget.tsx
 * 金融产业链因果推演沙盘：上下游指标调节、宏观冲击情景模拟与预期利润/系统风险测算看板
 */

import React from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Flame,
  RotateCcw,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react';
import type { FinancialShockScenario } from './artifactSandboxTypes';
import { useArtifactSandboxStore } from './useArtifactSandboxStore';

export interface FinancialSandplayWidgetProps {
  className?: string;
  onScenarioChange?: (scenario: FinancialShockScenario | null) => void;
}

const PRESET_SCENARIOS: FinancialShockScenario[] = [
  {
    id: 'supply_bottleneck',
    name: '上游供给断供冲击',
    description: '核心原材料成本上升 40%，中游产能压缩 15%',
    impactDeltas: {
      upstreamRawMaterialCost: 40,
      midstreamProcessingCapacity: -15,
    },
  },
  {
    id: 'demand_boom',
    name: '下游消费旺季井喷',
    description: '终端需求激增 50%，中游开工率提升 10%',
    impactDeltas: {
      downstreamEndUserDemand: 50,
      midstreamProcessingCapacity: 10,
    },
  },
  {
    id: 'tech_upgrade',
    name: '中游良率突破与降本',
    description: '加工成本降 20%，综合产能跃升 15%',
    impactDeltas: {
      upstreamRawMaterialCost: -20,
      midstreamProcessingCapacity: 15,
    },
  },
];

export const FinancialSandplayWidget: React.FC<FinancialSandplayWidgetProps> = ({
  className = '',
  onScenarioChange,
}) => {
  const baseMetrics = useArtifactSandboxStore(
    (state) => state.baseFinancialMetrics
  );
  const activeShock = useArtifactSandboxStore((state) => state.activeShock);
  const computedMetrics = useArtifactSandboxStore(
    (state) => state.computedFinancialMetrics
  );
  const setBaseFinancialMetrics = useArtifactSandboxStore(
    (state) => state.setBaseFinancialMetrics
  );
  const applyShockScenario = useArtifactSandboxStore(
    (state) => state.applyShockScenario
  );

  const handleApplyScenario = (scenario: FinancialShockScenario): void => {
    if (activeShock?.id === scenario.id) {
      applyShockScenario(null);
      if (onScenarioChange !== undefined) {
        onScenarioChange(null);
      }
    } else {
      applyShockScenario(scenario);
      if (onScenarioChange !== undefined) {
        onScenarioChange(scenario);
      }
    }
  };

  const handleResetMetrics = (): void => {
    setBaseFinancialMetrics({
      upstreamRawMaterialCost: 100,
      midstreamProcessingCapacity: 85,
      downstreamEndUserDemand: 120,
    });
    applyShockScenario(null);
    if (onScenarioChange !== undefined) {
      onScenarioChange(null);
    }
  };

  return (
    <section
      data-testid="financial-sandplay-widget"
      aria-label="金融产业链因果推演沙盘"
      className={`flex flex-col bg-slate-900 border border-slate-700/80 rounded-2xl shadow-xl p-4 gap-4 text-slate-200 ${className}`}
    >
      {/* 头部标题与重置 */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-emerald-400" />
          <div>
            <h2 className="text-sm font-semibold">
              产业链因果推演沙盘
            </h2>
            <p className="text-[11px] text-slate-400">
              多维参数调节与宏观冲击敏感度因果推演模型
            </p>
          </div>
        </div>

        <button
          type="button"
          data-testid="sandplay-reset-btn"
          aria-label="重置推演参数"
          onClick={handleResetMetrics}
          className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-400 hover:text-slate-200 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>重置参数</span>
        </button>
      </div>

      {/* 宏观冲击情景预设卡片 */}
      <fieldset className="flex flex-col gap-1.5">
        <legend className="text-xs font-medium text-slate-300">
          注入宏观冲击情景 (Macro Shock Scenarios):
        </legend>
        <div className="grid grid-cols-3 gap-2">
          {PRESET_SCENARIOS.map((scenario) => {
            const isSelected = activeShock?.id === scenario.id;
            return (
              <button
                key={scenario.id}
                type="button"
                data-testid={`scenario-btn-${scenario.id}`}
                onClick={() => handleApplyScenario(scenario)}
                className={`p-2 rounded-xl text-left border text-xs transition-all ${
                  isSelected
                    ? 'bg-amber-950/50 border-amber-500 ring-2 ring-amber-500/30'
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-1 font-semibold text-slate-200">
                  <Zap className="w-3.5 h-3.5 text-amber-400" />
                  <span>{scenario.name}</span>
                </div>
                <div className="text-[10px] text-slate-400 mt-1 line-clamp-2">
                  {scenario.description}
                </div>
              </button>
            );
          })}
        </div>
      </fieldset>

      {/* 产业链因果滑块调节区 */}
      <div className="grid grid-cols-3 gap-4 bg-slate-950/50 p-3 rounded-xl border border-slate-800">
        {/* 上游成本 */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs">
            <label
              htmlFor="upstream-cost-slider"
              className="text-slate-300 flex items-center gap-1"
            >
              <Flame className="w-3.5 h-3.5 text-red-400" />
              <span>上游原材料成本指数</span>
            </label>
            <span className="font-mono text-amber-400 font-bold">
              {computedMetrics.upstreamRawMaterialCost}
            </span>
          </div>
          <input
            id="upstream-cost-slider"
            data-testid="upstream-cost-slider"
            type="range"
            min="0"
            max="200"
            value={baseMetrics.upstreamRawMaterialCost}
            onChange={(e) =>
              setBaseFinancialMetrics({
                upstreamRawMaterialCost: Number(e.target.value),
              })
            }
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-red-500"
          />
        </div>

        {/* 中游产能 */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs">
            <label
              htmlFor="midstream-capacity-slider"
              className="text-slate-300 flex items-center gap-1"
            >
              <ArrowRight className="w-3.5 h-3.5 text-blue-400" />
              <span>中游产能利用率</span>
            </label>
            <span className="font-mono text-blue-400 font-bold">
              {computedMetrics.midstreamProcessingCapacity}%
            </span>
          </div>
          <input
            id="midstream-capacity-slider"
            data-testid="midstream-capacity-slider"
            type="range"
            min="0"
            max="100"
            value={baseMetrics.midstreamProcessingCapacity}
            onChange={(e) =>
              setBaseFinancialMetrics({
                midstreamProcessingCapacity: Number(e.target.value),
              })
            }
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
          />
        </div>

        {/* 下游需求 */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs">
            <label
              htmlFor="downstream-demand-slider"
              className="text-slate-300 flex items-center gap-1"
            >
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
              <span>下游终端需求指数</span>
            </label>
            <span className="font-mono text-emerald-400 font-bold">
              {computedMetrics.downstreamEndUserDemand}
            </span>
          </div>
          <input
            id="downstream-demand-slider"
            data-testid="downstream-demand-slider"
            type="range"
            min="0"
            max="200"
            value={baseMetrics.downstreamEndUserDemand}
            onChange={(e) =>
              setBaseFinancialMetrics({
                downstreamEndUserDemand: Number(e.target.value),
              })
            }
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
          />
        </div>
      </div>

      {/* 推演输出看板 */}
      <div className="grid grid-cols-2 gap-3">
        {/* 综合净利率预测 */}
        <div
          data-testid="projected-margin-card"
          className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between"
        >
          <div>
            <div className="text-[11px] text-slate-400">
              综合预期净利率 (Projected Margin)
            </div>
            <div
              className={`text-xl font-bold font-mono mt-1 ${
                computedMetrics.projectedProfitMargin >= 10
                  ? 'text-emerald-400'
                  : computedMetrics.projectedProfitMargin >= 0
                    ? 'text-amber-400'
                    : 'text-red-400'
              }`}
            >
              {computedMetrics.projectedProfitMargin}%
            </div>
          </div>
          {computedMetrics.projectedProfitMargin >= 10 ? (
            <TrendingUp className="w-7 h-7 text-emerald-400/80" />
          ) : (
            <TrendingDown className="w-7 h-7 text-amber-400/80" />
          )}
        </div>

        {/* 系统性供应链脆弱度 */}
        <div
          data-testid="risk-index-card"
          className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between"
        >
          <div>
            <div className="text-[11px] text-slate-400">
              系统性脆弱度指数 (Systemic Risk)
            </div>
            <div
              className={`text-xl font-bold font-mono mt-1 ${
                computedMetrics.systemicRiskIndex > 60
                  ? 'text-red-400'
                  : computedMetrics.systemicRiskIndex > 35
                    ? 'text-amber-400'
                    : 'text-emerald-400'
              }`}
            >
              {computedMetrics.systemicRiskIndex} / 100
            </div>
          </div>
          <AlertTriangle
            className={`w-7 h-7 ${
              computedMetrics.systemicRiskIndex > 60
                ? 'text-red-400/80'
                : 'text-amber-400/80'
            }`}
          />
        </div>
      </div>
    </section>
  );
};
