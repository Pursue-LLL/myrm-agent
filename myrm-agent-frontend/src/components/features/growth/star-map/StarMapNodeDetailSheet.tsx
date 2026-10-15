import React from 'react';
import {
  Star,
  Clock,
  ExternalLink,
  X,
  Layers,
  Tag,
  Activity,
  ShieldCheck,
  Bot,
  Globe,
} from 'lucide-react';
import { useStarMapStore } from './useStarMapStore';

export const StarMapNodeDetailSheet: React.FC = () => {
  const {
    nodes,
    links,
    selectedNodeId,
    isDetailSheetOpen,
    closeDetailSheet,
    openDetailSheet,
  } = useStarMapStore();

  if (!isDetailSheetOpen || !selectedNodeId) {
    return null;
  }

  const node = nodes.find((n) => n.id === selectedNodeId);
  if (!node) {
    return null;
  }

  const isSkill = node.type === 'skill';

  // 关联邻接节点
  const connectedLinks = links.filter(
    (l) => l.sourceId === node.id || l.targetId === node.id
  );
  const neighborIds = connectedLinks.map((l) =>
    l.sourceId === node.id ? l.targetId : l.sourceId
  );
  const neighbors = nodes.filter((n) => neighborIds.includes(n.id));

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />
      <dialog
        open
        aria-labelledby="node-detail-title"
        className="fixed inset-y-0 right-0 z-50 m-0 w-full max-w-md h-full bg-slate-900 border-l border-slate-700/80 shadow-2xl p-0 flex flex-col text-slate-100 overflow-hidden"
        data-testid="star-map-detail-sheet"
      >
        {/* 抽屉顶部头部 */}
        <header className="px-5 py-4 border-b border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            {isSkill ? (
              <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/40">
                <Star className="w-4 h-4 fill-current" />
              </div>
            ) : (
              <div className="p-2 rounded-lg bg-sky-500/20 text-sky-400 border border-sky-500/40">
                <Layers className="w-4 h-4" />
              </div>
            )}
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                  {isSkill ? '技能实体' : '记忆单元'}
                </span>
                <span className="text-[10px] text-slate-400 flex items-center space-x-1">
                  {node.scope === 'global' ? (
                    <>
                      <Globe className="w-3 h-3 text-emerald-400" />
                      <span>全局共享</span>
                    </>
                  ) : (
                    <>
                      <Bot className="w-3 h-3 text-indigo-400" />
                      <span>{node.agentId || '专属智能体'}</span>
                    </>
                  )}
                </span>
              </div>
              <h3 id="node-detail-title" className="font-bold text-sm text-white mt-0.5">
                {node.name}
              </h3>
            </div>
          </div>

          <button
            type="button"
            onClick={closeDetailSheet}
            aria-label="关闭节点详情"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 抽屉主体内容 */}
        <div className="flex-1 p-5 overflow-y-auto space-y-4 text-xs">
          {/* 核心指标看板 */}
          <div className="grid grid-cols-2 gap-2.5">
            <div className="p-2.5 rounded-lg bg-slate-950/50 border border-slate-800">
              <div className="flex items-center text-slate-400 mb-0.5 space-x-1">
                <Activity className="w-3 h-3 text-indigo-400" />
                <span>实战召回/使用次数</span>
              </div>
              <div className="text-base font-bold text-white font-mono">
                {node.recallCount} 次
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-950/50 border border-slate-800">
              <div className="flex items-center text-slate-400 mb-0.5 space-x-1">
                <Clock className="w-3 h-3 text-sky-400" />
                <span>学习沉淀时间</span>
              </div>
              <div className="text-xs font-semibold text-slate-200 mt-1">
                {new Date(node.createdAt).toLocaleDateString()}
              </div>
            </div>
          </div>

          {/* 实体描述 */}
          <div className="space-y-1">
            <div className="font-semibold text-slate-300">概要说明</div>
            <p className="text-slate-300 leading-relaxed bg-slate-950/40 p-3 rounded-lg border border-slate-800/80">
              {node.summary}
            </p>
          </div>

          {/* 来源溯源会话 */}
          {node.sourceChatId && (
            <div className="p-3 rounded-lg bg-indigo-950/30 border border-indigo-800/50 flex items-center justify-between">
              <div>
                <div className="text-[11px] text-indigo-300 font-semibold">
                  真实来源溯源会话
                </div>
                <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                  {node.sourceChatId}
                </div>
              </div>
              <button
                type="button"
                aria-label="跳转至来源会话"
                className="px-2.5 py-1 text-[11px] font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded flex items-center space-x-1"
              >
                <span>追溯</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            </div>
          )}

          {/* 标签 */}
          {node.tags.length > 0 && (
            <div className="space-y-1.5">
              <div className="font-semibold text-slate-300 flex items-center space-x-1">
                <Tag className="w-3 h-3 text-slate-400" />
                <span>知识分类与标签</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {node.tags.map((t) => (
                  <span
                    key={t}
                    className="px-2 py-0.5 rounded text-[11px] bg-slate-800 text-slate-300 border border-slate-700"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 关联星图邻居节点 */}
          {neighbors.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <div className="font-semibold text-slate-300 flex items-center justify-between">
                <span>邻接演化与共生节点 ({neighbors.length})</span>
                <span className="text-[10px] text-slate-500 font-mono">点击就地切换</span>
              </div>
              <div className="space-y-1.5">
                {neighbors.map((nb) => (
                  <button
                    type="button"
                    key={nb.id}
                    onClick={() => openDetailSheet(nb.id)}
                    aria-label={`切换查看邻接节点：${nb.name}`}
                    className="w-full p-2 rounded bg-slate-950/60 hover:bg-slate-800 border border-slate-800 hover:border-indigo-500/50 flex items-center justify-between text-left transition-colors"
                  >
                    <div className="flex items-center space-x-2">
                      {nb.type === 'skill' ? (
                        <Star className="w-3 h-3 text-amber-400 fill-current" />
                      ) : (
                        <Layers className="w-3 h-3 text-sky-400" />
                      )}
                      <span className="text-xs text-slate-200 font-medium truncate max-w-[200px]">
                        {nb.name}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400">
                      {nb.recallCount}次召回
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 底部无损治理操作区 */}
        <footer className="px-5 py-3 border-t border-slate-800 bg-slate-950/70 flex items-center justify-between text-xs">
          <div className="text-[11px] text-slate-400 flex items-center space-x-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>就地安全治理</span>
          </div>
          <button
            type="button"
            onClick={closeDetailSheet}
            className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded transition-colors"
          >
            完成查看
          </button>
        </footer>
      </dialog>
    </>
  );
};
