import React from 'react';
import {
  Sparkles,
  Zap,
  Play,
  ChevronDown,
  ChevronUp,
  X,
  Cpu,
  TrendingUp,
  CheckCircle2,
} from 'lucide-react';
import { useModelSpotlightStore } from './useModelSpotlightStore';
import {
  filterAvailableSpotlights,
  formatTokenCount,
} from './spotlightCatalogData';
import { SpotlightBadgeType } from './modelSpotlightTypes';

export function getBadgeLabel(badge: SpotlightBadgeType): string {
  switch (badge) {
    case 'flagship':
      return '旗舰突破';
    case 'discount':
      return '限时特惠';
    case 'reasoning':
      return '深度推理';
    case 'open-weights':
      return '开源权重';
    case 'multimodal':
      return '全模态';
    case 'ultra-fast':
      return '极速低延迟';
    default:
      return '前沿发布';
  }
}

export const HeroSpotlightMotionBanner: React.FC = () => {
  const {
    catalog,
    activeSpotlightId,
    dismissedRecords,
    isBannerCollapsed,
    setActiveSpotlight,
    toggleBannerCollapsed,
    dismissSpotlight,
    openPlayground,
    openMountModal,
  } = useModelSpotlightStore();

  const availableSpotlights = filterAvailableSpotlights(catalog, dismissedRecords);

  if (availableSpotlights.length === 0) {
    return null;
  }

  const activeSpotlight =
    availableSpotlights.find((item) => item.id === activeSpotlightId) ||
    availableSpotlights[0];

  if (isBannerCollapsed) {
    return (
      <div
        className="w-full bg-slate-900/90 text-slate-100 border-b border-indigo-500/30 px-4 py-2 backdrop-blur-md flex items-center justify-between shadow-sm transition-all"
        data-testid="spotlight-banner-collapsed"
      >
        <div className="flex items-center space-x-2 text-xs">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
          <span className="font-semibold text-indigo-300">
            前沿上新：{activeSpotlight.name}
          </span>
          <span className="text-slate-400 hidden sm:inline">
            ({formatTokenCount(activeSpotlight.contextWindow)} 上下文)
          </span>
        </div>
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => openPlayground(activeSpotlight)}
            aria-label="一键热试用"
            className="px-2 py-0.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium flex items-center space-x-1"
          >
            <Play className="w-3 h-3 fill-current" />
            <span>试用</span>
          </button>
          <button
            type="button"
            onClick={toggleBannerCollapsed}
            aria-label="展开聚光灯横幅"
            className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded"
          >
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <section
      aria-label="前沿模型发布动态聚光灯"
      className={`w-full relative overflow-hidden bg-gradient-to-r ${activeSpotlight.spotlightGradient.from} ${activeSpotlight.spotlightGradient.to} border-b ${activeSpotlight.spotlightGradient.accent} backdrop-blur-lg text-slate-100 shadow-md transition-all duration-300`}
      data-testid="spotlight-banner-expanded"
    >
      <div className="max-w-7xl mx-auto px-4 py-3 sm:px-6">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3">
          {/* 左侧：发布标识与核心描述 */}
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1.5">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-400/30">
                <Sparkles className="w-3 h-3 mr-1 text-indigo-400" />
                前沿聚光灯
              </span>
              <span className="text-xs text-slate-400 font-medium">
                {activeSpotlight.provider}
              </span>
              {activeSpotlight.highlightBadges.map((badge) => (
                <span
                  key={badge}
                  className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-800/60 text-slate-300 border border-slate-700/50"
                >
                  {getBadgeLabel(badge)}
                </span>
              ))}
              {activeSpotlight.discountPercent && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  <TrendingUp className="w-3 h-3 mr-1" />
                  限时减免 {activeSpotlight.discountPercent}%
                </span>
              )}
            </div>

            <div className="flex items-baseline space-x-2">
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                {activeSpotlight.name}
              </h2>
              <span className="text-xs text-slate-300 hidden md:inline">
                {activeSpotlight.tagline}
              </span>
            </div>

            {/* 基准跑分指标胶囊 */}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <div className="inline-flex items-center text-xs bg-slate-900/60 px-2 py-1 rounded border border-slate-700/60 text-slate-300">
                <Cpu className="w-3 h-3 mr-1 text-sky-400" />
                <span>上下文：{formatTokenCount(activeSpotlight.contextWindow)}</span>
              </div>
              {activeSpotlight.benchmarks.map((bench) => (
                <div
                  key={bench.label}
                  className="inline-flex items-center text-xs bg-slate-900/60 px-2 py-1 rounded border border-slate-700/60 text-slate-300"
                >
                  <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-400" />
                  <span className="font-medium mr-1">{bench.label}:</span>
                  <span className="text-emerald-300 font-bold">{bench.score}</span>
                  <span className="text-slate-400 text-[10px] ml-1">({bench.vsPrior})</span>
                </div>
              ))}
            </div>
          </div>

          {/* 右侧：操作区与选项卡 */}
          <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto justify-end">
            {availableSpotlights.length > 1 && (
              <div
                className="flex items-center bg-slate-900/70 p-0.5 rounded border border-slate-700/60 mr-1"
                role="tablist"
                aria-label="前沿模型列表切换"
              >
                {availableSpotlights.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={item.id === activeSpotlight.id}
                    onClick={() => setActiveSpotlight(item.id)}
                    className={`px-2 py-1 text-xs rounded transition-colors font-medium ${
                      item.id === activeSpotlight.id
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {item.name.split(' ')[0]}
                  </button>
                ))}
              </div>
            )}

            <button
              type="button"
              onClick={() => openPlayground(activeSpotlight)}
              aria-label="一键热试用临时沙箱"
              className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-md shadow flex items-center space-x-1.5 transition-all"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>立即试用</span>
            </button>

            <button
              type="button"
              onClick={() => openMountModal(activeSpotlight)}
              aria-label="一键热挂载至当前智能体"
              className="px-3 py-1.5 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-indigo-500/40 rounded-md shadow-sm flex items-center space-x-1.5 transition-all"
            >
              <Zap className="w-3.5 h-3.5 text-amber-400 fill-current" />
              <span>挂载至智能体</span>
            </button>

            <div className="flex items-center pl-1 border-l border-slate-700/60 space-x-1">
              <button
                type="button"
                onClick={toggleBannerCollapsed}
                aria-label="折叠聚光灯横幅"
                className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded"
              >
                <ChevronUp className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => dismissSpotlight(activeSpotlight.id, false)}
                aria-label="关闭本条聚光灯公告"
                className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800/60 rounded"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
