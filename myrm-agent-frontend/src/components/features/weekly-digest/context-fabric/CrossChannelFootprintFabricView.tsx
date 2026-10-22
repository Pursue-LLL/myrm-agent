import React from 'react';
import {
  Calendar,
  Sparkles,
  Layers,
  GitPullRequest,
  CheckCircle2,
  FileCode,
  BookOpen,
  AlertTriangle,
  ExternalLink,
  MessageSquare,
  Terminal,
  Monitor,
  CheckSquare,
  Square,
} from 'lucide-react';
import { useWeeklyDigestStore } from './useWeeklyDigestStore';
import {
  computeFootprintStats,
  filterFootprintsByChannel,
  filterFootprintsByCategory,
  getChannelDisplayName,
  getCategoryDisplayName,
} from './footprintAggregatorData';
import {
  ChannelType,
  FootprintCategory,
  ChannelFootprintItem,
} from './weeklyDigestTypes';

export function getChannelIcon(channel: ChannelType): React.ReactNode {
  switch (channel) {
    case 'feishu':
      return <MessageSquare className="w-3.5 h-3.5 text-blue-400" />;
    case 'wechat':
      return <MessageSquare className="w-3.5 h-3.5 text-emerald-400" />;
    case 'desktop':
      return <Monitor className="w-3.5 h-3.5 text-purple-400" />;
    case 'cli':
      return <Terminal className="w-3.5 h-3.5 text-amber-400" />;
    case 'web':
    default:
      return <Layers className="w-3.5 h-3.5 text-sky-400" />;
  }
}

export function getCategoryIcon(category: FootprintCategory): React.ReactNode {
  switch (category) {
    case 'pr-review':
      return <GitPullRequest className="w-3.5 h-3.5 text-blue-400" />;
    case 'deliverable':
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
    case 'rfc-decision':
      return <FileCode className="w-3.5 h-3.5 text-indigo-400" />;
    case 'learning':
      return <BookOpen className="w-3.5 h-3.5 text-amber-400" />;
    case 'risk-roadblock':
      return <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />;
    default:
      return <Layers className="w-3.5 h-3.5 text-slate-400" />;
  }
}

export const CrossChannelFootprintFabricView: React.FC = () => {
  const {
    footprints,
    selectedChannelFilter,
    selectedCategoryFilter,
    selectedWeekIdentifier,
    setChannelFilter,
    setCategoryFilter,
    toggleFootprintIncluded,
    setAllFootprintsIncluded,
    openSynthesizerModal,
  } = useWeeklyDigestStore();

  const stats = computeFootprintStats(footprints);

  const filteredItems = filterFootprintsByCategory(
    filterFootprintsByChannel(footprints, selectedChannelFilter),
    selectedCategoryFilter
  );

  const allSelected =
    footprints.length > 0 && footprints.every((item) => item.includedInDigest);

  const handleToggleSelectAll = () => {
    setAllFootprintsIncluded(!allSelected);
  };

  const channelOptions: Array<{ id: ChannelType | 'all'; label: string }> = [
    { id: 'all', label: `全部 (${stats.totalCount})` },
    { id: 'feishu', label: `飞书 (${stats.channelCounts.feishu})` },
    { id: 'desktop', label: `桌面端 (${stats.channelCounts.desktop})` },
    { id: 'web', label: `WebUI (${stats.channelCounts.web})` },
    { id: 'cli', label: `CLI (${stats.channelCounts.cli})` },
    { id: 'wechat', label: `微信 (${stats.channelCounts.wechat})` },
  ];

  const categoryOptions: Array<{ id: FootprintCategory | 'all'; label: string }> = [
    { id: 'all', label: '全部类型' },
    { id: 'deliverable', label: '核心交付' },
    { id: 'pr-review', label: '代码评审' },
    { id: 'rfc-decision', label: '架构决策' },
    { id: 'learning', label: '经验沉淀' },
    { id: 'risk-roadblock', label: '卡点风险' },
  ];

  return (
    <section
      aria-label="跨渠道上下文共享与工作足迹看板"
      className="w-full bg-slate-900 border border-slate-800 rounded-xl p-5 text-slate-100 shadow-lg space-y-4"
      data-testid="footprint-fabric-view"
    >
      {/* 顶部标题与行动栏 */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <Calendar className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-base font-bold text-white tracking-tight">
                全域工作足迹汇聚看板
              </h2>
              <span className="text-xs px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 font-mono border border-indigo-800/60">
                {selectedWeekIdentifier}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              自动汇聚飞书、微信、桌面端、WebUI 与 CLI 沉淀的工作事实，已纳入{' '}
              {stats.includedCount}/{stats.totalCount} 项
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={handleToggleSelectAll}
            className="px-2.5 py-1.5 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded border border-slate-700/60 flex items-center space-x-1.5 transition-colors"
          >
            {allSelected ? (
              <CheckSquare className="w-3.5 h-3.5 text-indigo-400" />
            ) : (
              <Square className="w-3.5 h-3.5 text-slate-400" />
            )}
            <span>{allSelected ? '取消全选' : '全选纳入'}</span>
          </button>
          <button
            type="button"
            onClick={openSynthesizerModal}
            aria-label="一键合成工作周报"
            className="px-3.5 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg shadow flex items-center space-x-1.5 transition-all"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>一键生成周报</span>
          </button>
        </div>
      </header>

      {/* 渠道过滤器选项卡 */}
      <div
        className="flex items-center space-x-1 overflow-x-auto pb-1 text-xs"
        role="tablist"
        aria-label="渠道过滤"
      >
        {channelOptions.map((opt) => (
          <button
            key={opt.id}
            type="button"
            role="tab"
            aria-selected={selectedChannelFilter === opt.id}
            onClick={() => setChannelFilter(opt.id)}
            className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition-colors ${
              selectedChannelFilter === opt.id
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* 类别微型标签过滤 */}
      <div className="flex items-center gap-1.5 flex-wrap text-xs">
        {categoryOptions.map((cat) => (
          <button
            key={cat.id}
            type="button"
            onClick={() => setCategoryFilter(cat.id)}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
              selectedCategoryFilter === cat.id
                ? 'bg-slate-700 text-white border-slate-500'
                : 'bg-slate-800/40 text-slate-400 border-slate-700/50 hover:text-slate-300'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* 足迹项目列表 */}
      <div className="space-y-2.5" data-testid="footprint-items-list">
        {filteredItems.length === 0 ? (
          <div className="text-center py-10 bg-slate-950/40 rounded-lg border border-slate-800 text-slate-500 text-xs">
            该筛选条件下暂无沉淀足迹
          </div>
        ) : (
          filteredItems.map((item: ChannelFootprintItem) => (
            <div
              key={item.id}
              className={`p-3 rounded-lg border transition-all flex items-start space-x-3 ${
                item.includedInDigest
                  ? 'bg-slate-800/60 border-slate-700/80 shadow-sm'
                  : 'bg-slate-900/40 border-slate-800/60 opacity-60'
              }`}
            >
              <button
                type="button"
                onClick={() => toggleFootprintIncluded(item.id)}
                aria-label={item.includedInDigest ? '从周报中排除' : '纳入周报'}
                className="mt-0.5 text-slate-400 hover:text-indigo-400 shrink-0"
              >
                {item.includedInDigest ? (
                  <CheckSquare className="w-4 h-4 text-indigo-400" />
                ) : (
                  <Square className="w-4 h-4 text-slate-500" />
                )}
              </button>

              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] bg-slate-900 text-slate-300 border border-slate-700/60">
                    {getChannelIcon(item.channel)}
                    <span>{getChannelDisplayName(item.channel)}</span>
                  </span>
                  <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] bg-slate-900 text-slate-300 border border-slate-700/60">
                    {getCategoryIcon(item.category)}
                    <span>{getCategoryDisplayName(item.category)}</span>
                  </span>
                </div>

                <h3 className="text-xs font-semibold text-slate-100 mb-0.5">
                  {item.title}
                </h3>
                <p className="text-xs text-slate-300 leading-relaxed">
                  {item.description}
                </p>

                <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
                  {item.metrics && (
                    <span className="text-emerald-300 bg-emerald-950/40 px-1.5 py-0.5 rounded border border-emerald-800/50">
                      指标：{item.metrics}
                    </span>
                  )}
                  {item.artifactRef && (
                    <span className="inline-flex items-center space-x-0.5 text-sky-400 hover:underline">
                      <ExternalLink className="w-2.5 h-2.5" />
                      <span className="truncate max-w-[200px]">{item.artifactRef}</span>
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
};
