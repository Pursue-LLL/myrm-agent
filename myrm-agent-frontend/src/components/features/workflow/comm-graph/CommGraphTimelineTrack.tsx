import React from 'react';
import {
  Radio,
  History,
  ArrowRight,
  Clock,
  CheckCircle2,
  AlertCircle,
  CornerUpLeft,
} from 'lucide-react';
import { useCommGraphStore } from './useCommGraphStore';
import type { AgentCommEvent } from './commGraphTypes';

export const CommGraphTimelineTrack: React.FC = () => {
  const {
    events,
    selectedEventId,
    isLive,
    returnCursorId,
    selectEvent,
    toggleLive,
  } = useCommGraphStore();

  if (events.length === 0) {
    return null;
  }

  const selectedEvent =
    events.find((e) => e.id === selectedEventId) ?? events[events.length - 1];

  const returnEvent = events.find((e) => e.id === returnCursorId);

  return (
    <div className="w-full space-y-4">
      {/* 顶栏控制条与 Live 双向游标切换器 */}
      <div className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-200">
            协同流水线事件 ({events.length})
          </span>
          <span className="text-slate-600">•</span>
          <span className="text-xs text-slate-400">
            {isLive ? (
              <span className="text-emerald-400 font-medium">
                正在实时吸附最新协同动态
              </span>
            ) : (
              <span className="text-indigo-300 font-medium">
                历史审阅模式 (已暂停自动跟随)
              </span>
            )}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* 双向记忆提示 */}
          {!isLive && returnCursorId !== null && returnEvent && (
            <span className="hidden md:inline-flex items-center gap-1 text-[11px] text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700">
              <CornerUpLeft className="h-3 w-3 text-indigo-400" />
              已记忆回溯点: 步骤 #{returnEvent.stepIndex}
            </span>
          )}

          {/* Live 双向切换按钮 */}
          <button
            type="button"
            onClick={toggleLive}
            aria-label={
              isLive
                ? '退出实时追踪模式并回溯历史游标'
                : '切入实时追踪最新事件'
            }
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
              isLive
                ? 'border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 shadow-sm shadow-emerald-950'
                : 'border border-slate-700 bg-slate-800/90 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
            }`}
          >
            {isLive ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
                <Radio className="h-3.5 w-3.5 text-emerald-400" />
                <span>Live 实时跟随中</span>
              </>
            ) : (
              <>
                <History className="h-3.5 w-3.5 text-slate-400" />
                <span>
                  切入 Live
                  {returnCursorId !== null ? ' (记忆回溯)' : ''}
                </span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 横向步骤时间轴轨道 */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 pt-1 scrollbar-thin">
        {events.map((evt) => {
          const isSelected = evt.id === selectedEvent.id;
          const isReturnPoint = evt.id === returnCursorId;

          return (
            <button
              key={evt.id}
              type="button"
              onClick={() => {
                selectEvent(evt.id);
              }}
              className={`group relative flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-left transition-all ${
                isSelected
                  ? 'border-indigo-500 bg-indigo-600/15 shadow-sm ring-1 ring-indigo-500/50'
                  : 'border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-800/60'
              }`}
            >
              <div
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                  isSelected
                    ? 'bg-indigo-500 text-white'
                    : 'bg-slate-800 text-slate-400 group-hover:bg-slate-700 group-hover:text-slate-200'
                }`}
              >
                {evt.stepIndex}
              </div>

              <div className="text-xs">
                <div
                  className={`font-medium ${
                    isSelected ? 'text-white' : 'text-slate-300'
                  }`}
                >
                  {evt.action}
                </div>
                <div className="text-[10px] text-slate-400">
                  {evt.fromAgent.split(' ')[0]} → {evt.toAgent.split(' ')[0]}
                </div>
              </div>

              {isReturnPoint && !isSelected && (
                <span
                  title="上次审阅的历史游标"
                  className="absolute -top-1 -right-1 flex h-2.5 w-2.5 rounded-full bg-indigo-400 ring-2 ring-slate-900"
                />
              )}
            </button>
          );
        })}
      </div>

      {/* 选定事件的详细协同面板 */}
      {selectedEvent && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 text-xs">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <span className="rounded bg-indigo-500/20 px-2 py-0.5 font-mono text-[11px] font-semibold text-indigo-300 border border-indigo-500/30">
                步骤 #{selectedEvent.stepIndex}
              </span>
              <span className="font-semibold text-slate-200">
                {selectedEvent.action}
              </span>
            </div>

            <div className="flex items-center gap-3 text-slate-400">
              {selectedEvent.latencyMs !== undefined && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {selectedEvent.latencyMs}ms
                </span>
              )}
              <span className="inline-flex items-center gap-1 text-emerald-400">
                {selectedEvent.status === 'completed' ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <AlertCircle className="h-3.5 w-3.5 text-amber-400" />
                )}
                {selectedEvent.status}
              </span>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div className="rounded-lg bg-slate-800/40 p-2.5 border border-slate-800/60">
              <div className="text-[11px] text-slate-400">发起方智能体</div>
              <div className="font-medium text-slate-200 mt-0.5">
                {selectedEvent.fromAgent}
              </div>
            </div>
            <div className="rounded-lg bg-slate-800/40 p-2.5 border border-slate-800/60">
              <div className="text-[11px] text-slate-400">接收方智能体</div>
              <div className="font-medium text-slate-200 mt-0.5">
                {selectedEvent.toAgent}
              </div>
            </div>
          </div>

          <div className="mt-3 rounded-lg bg-slate-950/70 p-3 font-mono text-slate-300 border border-slate-800">
            <div className="text-[10px] text-slate-400 mb-1">
              通信载荷摘要 (Payload Summary):
            </div>
            <div className="leading-relaxed">{selectedEvent.payloadSummary}</div>
          </div>
        </div>
      )}
    </div>
  );
};
