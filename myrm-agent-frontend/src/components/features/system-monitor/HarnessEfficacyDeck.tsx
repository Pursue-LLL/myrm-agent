/**
 * [INPUT]: assets (AssetFrictionMetric[]), onSelectDossier? ((skillId: string) => void).
 * [OUTPUT]: Immersive efficacy and asset friction dashboard with stratified model filtering, core vs assassin tags, and governance advice.
 * [POS]: myrm-agent-frontend/src/components/features/system-monitor/HarnessEfficacyDeck.tsx
 */

import React, { useMemo, useState } from 'react';
import {
  AssetFrictionMetric,
  AssetHealthTag,
  ExecutionMode,
} from './deliveryDossierTypes';

export interface HarnessEfficacyDeckProps {
  assets: AssetFrictionMetric[];
  onInspectSkill?: (skillId: string, modelName: string) => void;
}

const TAG_STYLES: Record<AssetHealthTag, { label: string; badgeClass: string }> = {
  CORE_EFFICIENT: {
    label: '🌟 核心高效资产',
    badgeClass: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-300 dark:border-emerald-700',
  },
  FRICTION_ASSASSIN: {
    label: '⚠️ 摩擦刺客资产',
    badgeClass: 'bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300 border-red-300 dark:border-red-700',
  },
  NORMAL: {
    label: '基线正常',
    badgeClass: 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 border-blue-200 dark:border-blue-800',
  },
  SAMPLE_INSUFFICIENT: {
    label: '样本不足',
    badgeClass: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 border-gray-200 dark:border-gray-700',
  },
};

export const HarnessEfficacyDeck: React.FC<HarnessEfficacyDeckProps> = ({
  assets,
  onInspectSkill,
}) => {
  const [selectedModel, setSelectedModel] = useState<string>('ALL');
  const [selectedMode, setSelectedMode] = useState<string>('ALL');

  // Extract unique model list for stratified filtering
  const modelOptions = useMemo(() => {
    const set = new Set<string>();
    assets.forEach((a) => set.add(a.model_name));
    return Array.from(set);
  }, [assets]);

  const filteredAssets = useMemo(() => {
    return assets.filter((a) => {
      const matchModel = selectedModel === 'ALL' || a.model_name === selectedModel;
      const matchMode = selectedMode === 'ALL' || a.execution_mode === selectedMode;
      return matchModel && matchMode;
    });
  }, [assets, selectedModel, selectedMode]);

  const summary = useMemo(() => {
    const coreCount = filteredAssets.filter((a) => a.health_tag === 'CORE_EFFICIENT').length;
    const assassinCount = filteredAssets.filter((a) => a.health_tag === 'FRICTION_ASSASSIN').length;
    const totalWastedTokens = filteredAssets.reduce((sum, a) => sum + a.total_wasted_tokens, 0);
    return { coreCount, assassinCount, totalWastedTokens };
  }, [filteredAssets]);

  return (
    <div
      className="p-5 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm space-y-5"
      data-testid="harness-efficacy-deck"
    >
      {/* Header & High-level KPIs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-100 dark:border-gray-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">📊</span>
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              跨智能体资产健康与效能大盘 (Better Harness 视角)
            </h2>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            拒绝表面调用率繁荣 · 按模型分层度量真实采纳率与摩擦返工浪费
          </p>
        </div>

        {/* Filter Controls */}
        <div className="flex items-center gap-2 text-xs">
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-lg text-gray-700 dark:text-gray-300 focus:outline-none"
            data-testid="model-filter-select"
          >
            <option value="ALL">全部模型分层</option>
            {modelOptions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>

          <select
            value={selectedMode}
            onChange={(e) => setSelectedMode(e.target.value)}
            className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-lg text-gray-700 dark:text-gray-300 focus:outline-none"
            data-testid="mode-filter-select"
          >
            <option value="ALL">全部执行模式</option>
            <option value="MULTI_TURN_AGENT">多轮 Agent 会话</option>
            <option value="SINGLE_SHOT">单次生成</option>
          </select>
        </div>
      </div>

      {/* KPI Metric Summary Cards */}
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div className="p-3 bg-emerald-50/50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/40 rounded-lg">
          <div className="text-emerald-700 dark:text-emerald-300 font-medium">核心高效资产</div>
          <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-1" data-testid="core-count">
            {summary.coreCount} <span className="text-xs font-normal">个技能</span>
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">高采纳 (≥80%) / 极低返工</div>
        </div>

        <div className="p-3 bg-red-50/50 dark:bg-red-950/20 border border-red-200 dark:border-red-800/40 rounded-lg">
          <div className="text-red-700 dark:text-red-300 font-medium">摩擦刺客资产</div>
          <div className="text-xl font-bold text-red-600 dark:text-red-400 mt-1" data-testid="assassin-count">
            {summary.assassinCount} <span className="text-xs font-normal">个技能</span>
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">频繁死循环 / 建议降级下线</div>
        </div>

        <div className="p-3 bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/40 rounded-lg">
          <div className="text-amber-700 dark:text-amber-300 font-medium">累计沉没摩擦损耗</div>
          <div className="text-xl font-bold text-amber-600 dark:text-amber-400 mt-1" data-testid="total-wasted-tokens">
            {summary.totalWastedTokens.toLocaleString()} <span className="text-xs font-normal">Tokens</span>
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">异常重试与产物打回浪费</div>
        </div>
      </div>

      {/* Stratified Asset Table */}
      <div className="overflow-x-auto border border-gray-100 dark:border-gray-800 rounded-lg">
        <table className="w-full text-left text-xs" data-testid="assets-table">
          <thead className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 dark:text-gray-400 uppercase text-[10px]">
            <tr>
              <th className="py-2.5 px-3">技能资产 (Skill)</th>
              <th className="py-2.5 px-3">模型分桶</th>
              <th className="py-2.5 px-3 text-center">样本量</th>
              <th className="py-2.5 px-3 text-center">真实采纳率</th>
              <th className="py-2.5 px-3 text-center">摩擦指数</th>
              <th className="py-2.5 px-3 text-center">沉没损耗</th>
              <th className="py-2.5 px-3">健康治理结论</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800 font-mono text-[11px]">
            {filteredAssets.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-6 text-center text-gray-400 italic">
                  暂无匹配的资产度量记录
                </td>
              </tr>
            ) : (
              filteredAssets.map((asset, idx) => {
                const tagConfig = TAG_STYLES[asset.health_tag] || TAG_STYLES.NORMAL;
                return (
                  <tr
                    key={idx}
                    className="hover:bg-gray-50/60 dark:hover:bg-gray-800/30 transition-colors cursor-pointer"
                    onClick={() => onInspectSkill?.(asset.skill_id, asset.model_name)}
                    data-testid={`asset-row-${asset.skill_id}-${asset.model_name}`}
                  >
                    <td className="py-2.5 px-3 font-semibold text-gray-900 dark:text-gray-100">
                      {asset.skill_id}
                    </td>
                    <td className="py-2.5 px-3 text-gray-600 dark:text-gray-300">
                      {asset.model_name}
                    </td>
                    <td className="py-2.5 px-3 text-center text-gray-500">
                      {asset.sample_count}
                    </td>
                    <td className="py-2.5 px-3 text-center font-bold">
                      <span
                        className={
                          asset.true_efficacy_rate_pct >= 80
                            ? 'text-emerald-600'
                            : asset.true_efficacy_rate_pct <= 40
                            ? 'text-red-600'
                            : 'text-gray-700 dark:text-gray-300'
                        }
                      >
                        {asset.true_efficacy_rate_pct}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <span
                        className={`font-semibold ${
                          asset.friction_index >= 0.6
                            ? 'text-red-500'
                            : asset.friction_index <= 0.25
                            ? 'text-emerald-600'
                            : 'text-gray-600 dark:text-gray-400'
                        }`}
                      >
                        {asset.friction_index.toFixed(2)}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-center text-red-500">
                      {asset.total_wasted_tokens > 0 ? `${asset.total_wasted_tokens} T` : '0'}
                    </td>
                    <td className="py-2.5 px-3 font-sans">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`px-2 py-0.5 text-[10px] font-bold border rounded ${tagConfig.badgeClass}`}
                        >
                          {tagConfig.label}
                        </span>
                      </div>
                      <div className="text-[10px] text-gray-400 mt-0.5 truncate max-w-xs" title={asset.governance_advice}>
                        {asset.governance_advice}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
