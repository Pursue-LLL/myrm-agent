import React from 'react';
import {
  Sparkles,
  Eye,
  EyeOff,
  Download,
  List,
  Layers,
  Star,
  ShieldCheck,
  CheckCircle2,
} from 'lucide-react';
import { useStarMapStore } from './useStarMapStore';
import {
  filterStarMapLinks,
  filterStarMapNodes,
} from './starMapCatalogData';
import { StarMapNode } from './starMapTypes';

export const RadialStarMapCanvas: React.FC = () => {
  const {
    nodes,
    links,
    selectedNodeId,
    hoveredNodeId,
    filter,
    playback,
    viewMode,
    setHoveredNodeId,
    openDetailSheet,
    toggleHideLabels,
    exportStarMapImage,
    setViewMode,
  } = useStarMapStore();

  const filteredNodes = filterStarMapNodes(nodes, filter);
  const visibleNodes = filteredNodes.filter(
    (node) => node.createdAt <= playback.currentCutoffTimestamp
  );
  const visibleNodeIdSet = new Set(visibleNodes.map((n) => n.id));
  const visibleLinks = filterStarMapLinks(links, visibleNodeIdSet);

  const isConnectedToHovered = (nodeId: string): boolean => {
    if (!hoveredNodeId) {
      return false;
    }
    if (nodeId === hoveredNodeId) {
      return true;
    }
    return visibleLinks.some(
      (l) =>
        (l.sourceId === hoveredNodeId && l.targetId === nodeId) ||
        (l.targetId === hoveredNodeId && l.sourceId === nodeId)
    );
  };

  const handleExport = async () => {
    await exportStarMapImage();
  };

  return (
    <section
      aria-label="学习星图全景画布"
      className="w-full bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-2xl relative text-slate-100 flex flex-col"
      data-testid="radial-star-map-canvas"
    >
      {/* 顶栏工具条 */}
      <header className="px-5 py-3 border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="p-1.5 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-sm font-bold text-white tracking-tight">
                AI 学习星图与演化全景
              </h2>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950/70 text-amber-300 font-medium border border-amber-800/50">
                金星 = 技能 · 蓝钻 = 记忆
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">
              同心圆径向布局：最老居于中心，最新位于外环；已点亮 {visibleNodes.length}/{filteredNodes.length} 个节点
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={toggleHideLabels}
            aria-label={filter.hideLabels ? '显示节点文本' : '隐藏文本以脱敏'}
            className="px-2.5 py-1 text-xs text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-700 rounded border border-slate-700/60 flex items-center space-x-1.5 transition-colors"
          >
            {filter.hideLabels ? (
              <>
                <EyeOff className="w-3.5 h-3.5 text-amber-400" />
                <span className="hidden sm:inline">脱敏中 (无文字)</span>
              </>
            ) : (
              <>
                <Eye className="w-3.5 h-3.5 text-slate-400" />
                <span className="hidden sm:inline">明文显示</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={handleExport}
            aria-label="导出星图图片"
            className="px-2.5 py-1 text-xs text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-700 rounded border border-slate-700/60 flex items-center space-x-1.5 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">导出图片</span>
          </button>

          <div className="flex items-center bg-slate-800/80 p-0.5 rounded border border-slate-700/60">
            <button
              type="button"
              aria-label="切换至星图视图"
              onClick={() => setViewMode('map')}
              className={`p-1 rounded ${
                viewMode === 'map' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              aria-label="切换至列表视图"
              onClick={() => setViewMode('list')}
              className={`p-1 rounded ${
                viewMode === 'list' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </header>

      {/* 视图主体 */}
      {viewMode === 'list' ? (
        <div className="p-5 max-h-[500px] overflow-y-auto space-y-2" data-testid="star-map-list-view">
          {visibleNodes.map((node) => (
            <button
              type="button"
              key={node.id}
              onClick={() => openDetailSheet(node.id)}
              aria-label={`查看节点详情：${node.name}`}
              className="w-full text-left p-3 bg-slate-900/60 hover:bg-slate-850 border border-slate-800 hover:border-indigo-500/50 rounded-lg flex items-center justify-between transition-colors"
            >
              <div className="flex items-center space-x-3">
                {node.type === 'skill' ? (
                  <div className="w-6 h-6 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center border border-amber-500/40">
                    <Star className="w-3.5 h-3.5 fill-current" />
                  </div>
                ) : (
                  <div className="w-6 h-6 rotate-45 rounded bg-sky-500/20 text-sky-400 flex items-center justify-center border border-sky-500/40">
                    <div className="-rotate-45 text-[10px] font-bold">M</div>
                  </div>
                )}
                <div>
                  <div className="font-semibold text-xs text-slate-100">
                    {filter.hideLabels ? '••• 已脱敏 •••' : node.name}
                  </div>
                  <div className="text-[11px] text-slate-400">
                    {filter.hideLabels ? '内容已隐藏' : node.summary}
                  </div>
                </div>
              </div>
              <div className="text-right text-[11px] text-slate-400">
                <div>召回: {node.recallCount} 次</div>
                <div className="text-[10px] text-slate-500">{new Date(node.createdAt).toLocaleDateString()}</div>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div
          className="relative w-full aspect-square max-w-[600px] mx-auto p-4 flex items-center justify-center select-none"
          data-testid="star-map-svg-container"
        >
          <svg
            viewBox="0 0 600 600"
            className="w-full h-full overflow-visible"
            aria-label="径向时间同心圆学习星图"
          >
            <defs>
              <radialGradient id="star-map-glow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#6366f1" stopOpacity="0.15" />
                <stop offset="100%" stopColor="#0f172a" stopOpacity="0" />
              </radialGradient>
            </defs>

            {/* 背景氛围晕染 */}
            <circle cx="300" cy="300" r="280" fill="url(#star-map-glow)" />

            {/* 同心圆时间环（径向时间） */}
            {[70, 130, 190, 250].map((radius, idx) => (
              <g key={radius}>
                <circle
                  cx="300"
                  cy="300"
                  r={radius}
                  fill="none"
                  stroke="#334155"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                  opacity={0.6}
                />
                <text
                  x="305"
                  y={300 - radius + 12}
                  fill="#64748b"
                  fontSize="9"
                  fontFamily="sans-serif"
                >
                  {idx === 0 ? '初创原点' : idx === 1 ? '早期探索' : idx === 2 ? '中期复合' : '前沿最新'}
                </text>
              </g>
            ))}

            {/* 连线层 */}
            {visibleLinks.map((link) => {
              const src = visibleNodes.find((n) => n.id === link.sourceId);
              const tgt = visibleNodes.find((n) => n.id === link.targetId);
              if (!src?.radialPosition || !tgt?.radialPosition) {
                return null;
              }

              const isHighlighted =
                hoveredNodeId === link.sourceId || hoveredNodeId === link.targetId;

              return (
                <line
                  key={link.id}
                  x1={src.radialPosition.x}
                  y1={src.radialPosition.y}
                  x2={tgt.radialPosition.x}
                  y2={tgt.radialPosition.y}
                  stroke={isHighlighted ? '#818cf8' : '#334155'}
                  strokeWidth={isHighlighted ? 2 : 1}
                  strokeOpacity={isHighlighted ? 0.9 : 0.4}
                  strokeDasharray={link.relation === 'evolution' ? '2 2' : undefined}
                />
              );
            })}

            {/* 节点层 */}
            {visibleNodes.map((node: StarMapNode) => {
              const pos = node.radialPosition;
              if (!pos) {
                return null;
              }

              const isSelected = selectedNodeId === node.id;
              const isHovered = hoveredNodeId === node.id;
              const isConnected = isConnectedToHovered(node.id);
              const isSkill = node.type === 'skill';

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  className="cursor-pointer transition-transform duration-150"
                  onClick={() => openDetailSheet(node.id)}
                  onMouseEnter={() => setHoveredNodeId(node.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                  data-testid={`star-node-${node.id}`}
                >
                  {/* 悬停光晕 */}
                  {(isSelected || isHovered || isConnected) && (
                    <circle
                      r="16"
                      fill={isSkill ? '#f59e0b' : '#38bdf8'}
                      opacity={0.25}
                      className="animate-pulse"
                    />
                  )}

                  {/* 形状：技能金圆点 vs 记忆蓝菱形 */}
                  {isSkill ? (
                    <circle
                      r={isSelected || isHovered ? 8 : 6}
                      fill="#f59e0b"
                      stroke="#fbbf24"
                      strokeWidth="2"
                    />
                  ) : (
                    <rect
                      x={isSelected || isHovered ? -7 : -5}
                      y={isSelected || isHovered ? -7 : -5}
                      width={isSelected || isHovered ? 14 : 10}
                      height={isSelected || isHovered ? 14 : 10}
                      transform="rotate(45)"
                      fill="#0284c7"
                      stroke="#38bdf8"
                      strokeWidth="2"
                    />
                  )}

                  {/* 标签文字（脱敏开关可隐藏） */}
                  {!filter.hideLabels && (
                    <text
                      y="16"
                      textAnchor="middle"
                      fill={isSelected || isHovered ? '#ffffff' : '#94a3b8'}
                      fontSize="9"
                      fontWeight={isSelected || isHovered ? 'bold' : 'normal'}
                      className="pointer-events-none drop-shadow"
                    >
                      {node.name.length > 8 ? `${node.name.slice(0, 8)}…` : node.name}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </section>
  );
};
