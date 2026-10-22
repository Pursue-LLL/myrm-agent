import React from 'react';
import {
  Activity,
  Layers,
  Sparkles,
  ExternalLink,
  Bot,
  Send,
  FileCode,
  LayoutGrid,
} from 'lucide-react';
import { useMultiPaneCockpitStore } from './useMultiPaneCockpitStore';
import { BotRosterPane } from './BotRosterPane';
import { BotCronInspectorPane } from './BotCronInspectorPane';
import { ActiveBotPulseBadge } from './ActiveBotPulseBadge';

export const MultiPaneFlexibleCockpit: React.FC = () => {
  const {
    bots,
    selectedBotId,
    paneMode,
    isArtifactInspectorOpen,
    activeHandoffBotId,
    toggleCronInspector,
    toggleArtifactInspector,
  } = useMultiPaneCockpitStore();

  const selectedBot = bots.find((b) => b.id === selectedBotId) ?? bots[0];
  const activeBots = bots.filter((b) => b.pulse.isActive);

  return (
    <div
      aria-label="多栏自由桌面协同驾驶舱"
      className="flex h-screen w-full flex-col bg-slate-950 text-slate-100"
    >
      {/* 顶部全局协作状态条 */}
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900/90 px-4 backdrop-blur-md">
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5 text-xs font-semibold text-slate-200">
            <LayoutGrid className="h-4 w-4 text-blue-400" />
            <span>智能体多栏协同视界</span>
          </div>

          <div className="flex items-center space-x-2 border-l border-slate-800 pl-3">
            <div className="flex items-center space-x-1 text-[11px] text-slate-400">
              <Activity className="h-3.5 w-3.5 text-emerald-400" />
              <span>后台活跃:</span>
              <span className="font-semibold text-emerald-400">{activeBots.length}</span>
              <span>/ {bots.length}</span>
            </div>

            {activeBots.length > 0 && (
              <div className="flex items-center space-x-1">
                {activeBots.map((b) => (
                  <span
                    key={b.id}
                    className="inline-flex items-center space-x-1 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
                    <span>{b.name}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => {
              toggleCronInspector();
            }}
            className="inline-flex items-center space-x-1 rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            <Layers className="h-3.5 w-3.5 text-amber-400" />
            <span>定时面板</span>
          </button>

          {paneMode === 'four_pane' && (
            <button
              type="button"
              onClick={() => {
                toggleArtifactInspector();
              }}
              className="inline-flex items-center space-x-1 rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
            >
              <FileCode className="h-3.5 w-3.5 text-purple-400" />
              <span>工件反链</span>
            </button>
          )}
        </div>
      </header>

      {/* 主工作区多栏容器 */}
      <div className="flex flex-1 overflow-hidden">
        {/* Pane 1: Bot 团队名册 */}
        <BotRosterPane />

        {/* Pane 2: 中间主对话与任务现场 */}
        <main className="flex flex-1 flex-col overflow-hidden bg-slate-950">
          {/* Handoff 穿梭高亮提示条 */}
          {activeHandoffBotId === selectedBot.id && selectedBot.pulse.isActive && (
            <div className="flex items-center justify-between border-b border-amber-500/30 bg-amber-950/20 px-4 py-2 text-xs text-amber-300">
              <div className="flex items-center space-x-2">
                <Sparkles className="h-3.5 w-3.5 animate-spin text-amber-400" />
                <span className="font-medium">已秒级穿梭至「{selectedBot.name}」执行现场</span>
                <span className="text-slate-400">· {selectedBot.pulse.currentTaskTitle}</span>
              </div>
              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300">
                实时推流中
              </span>
            </div>
          )}

          {/* 会话顶部 Bot 信息栏 */}
          <div className="flex h-12 shrink-0 items-center justify-between border-b border-slate-800/80 px-4">
            <div className="flex items-center space-x-3">
              <ActiveBotPulseBadge
                pulse={selectedBot.pulse}
                avatarIconName={selectedBot.avatarIconName}
                size="sm"
              />
              <div>
                <h2 className="text-xs font-semibold text-slate-100">{selectedBot.name}</h2>
                <p className="text-[10px] text-slate-400">{selectedBot.role}</p>
              </div>
            </div>

            <div className="flex items-center space-x-2 text-xs text-slate-400">
              {selectedBot.pulse.isActive ? (
                <span className="inline-flex items-center space-x-1 text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
                  <span>执行中</span>
                </span>
              ) : (
                <span className="text-slate-500">待命中</span>
              )}
            </div>
          </div>

          {/* 消息与思维链执行展示流 */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
              <div className="flex items-center space-x-2 text-xs font-medium text-slate-300 mb-2">
                <Bot className="h-4 w-4 text-blue-400" />
                <span>智能体就绪状态与资产清单</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                当前挂载了 {selectedBot.cronJobs.length} 项专属定时任务。
                {selectedBot.latestOutputSummary && (
                  <span className="block mt-2 rounded bg-slate-950 p-2.5 font-mono text-[11px] text-slate-300 border border-slate-800">
                    最新输出摘要：{selectedBot.latestOutputSummary}
                  </span>
                )}
              </p>
            </div>
          </div>

          {/* 底部输入操作栏 */}
          <div className="shrink-0 border-t border-slate-800 p-3">
            <div className="flex items-center space-x-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2">
              <input
                type="text"
                placeholder={`向 ${selectedBot.name} 派发新任务或调整定时策略...`}
                className="flex-1 bg-transparent text-xs text-slate-100 placeholder-slate-500 focus:outline-none"
              />
              <button
                type="button"
                className="rounded-md bg-blue-600 p-1.5 text-white hover:bg-blue-500"
                aria-label="发送任务"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </main>

        {/* Pane 3: 专属 Cron 定时任务监控 */}
        <BotCronInspectorPane />

        {/* Pane 4: 四栏模式下的实时工件反链面板 */}
        {paneMode === 'four_pane' && isArtifactInspectorOpen && (
          <aside
            aria-label="工件实时预览面板"
            className="flex w-72 flex-col border-l border-slate-800 bg-slate-900/95 p-3"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-2 text-xs font-semibold text-slate-200">
              <div className="flex items-center space-x-1.5">
                <FileCode className="h-4 w-4 text-purple-400" />
                <span>工件实时预览</span>
              </div>
              <ExternalLink className="h-3.5 w-3.5 text-slate-400" />
            </div>
            <div className="mt-3 flex-1 overflow-y-auto rounded bg-slate-950/80 p-2 font-mono text-[11px] text-slate-400 border border-slate-800">
              暂未挂载新的实时代码工件
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};
