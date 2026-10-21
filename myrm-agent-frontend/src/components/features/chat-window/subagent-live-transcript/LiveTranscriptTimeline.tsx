import React from 'react';
import type { TranscriptEvent } from './types';

interface LiveTranscriptTimelineProps {
  events: TranscriptEvent[];
}

export const LiveTranscriptTimeline: React.FC<LiveTranscriptTimelineProps> = ({ events }) => {
  const getKindBadge = (kind: string) => {
    switch (kind) {
      case 'thought':
        return <span className="px-1.5 py-0.5 rounded text-xs bg-purple-900/40 text-purple-300 font-mono">💭 思考</span>;
      case 'tool_call':
        return <span className="px-1.5 py-0.5 rounded text-xs bg-blue-900/40 text-blue-300 font-mono">🛠️ 调用</span>;
      case 'tool_result':
        return <span className="px-1.5 py-0.5 rounded text-xs bg-emerald-900/40 text-emerald-300 font-mono">✅ 返回</span>;
      case 'approval_requested':
        return <span className="px-1.5 py-0.5 rounded text-xs bg-amber-900/40 text-amber-300 font-mono">⚠️ 待审批</span>;
      case 'approval_resolved':
        return <span className="px-1.5 py-0.5 rounded text-xs bg-cyan-900/40 text-cyan-300 font-mono">🛡️ 审批结果</span>;
      case 'denied_feedback':
        return <span className="px-1.5 py-0.5 rounded text-xs bg-rose-900/40 text-rose-300 font-mono">🛑 /deny 反馈</span>;
      case 'error':
        return <span className="px-1.5 py-0.5 rounded text-xs bg-red-900/40 text-red-300 font-mono">❌ 异常</span>;
      default:
        return <span className="px-1.5 py-0.5 rounded text-xs bg-zinc-800 text-zinc-400 font-mono">📝 {kind}</span>;
    }
  };

  return (
    <div className="space-y-2 mt-3">
      <div className="flex items-center justify-between text-xs text-zinc-400 border-b border-zinc-800 pb-1">
        <span>实时执行轨迹 (Live Transcript Stream)</span>
        <span>共 {events.length} 个事件</span>
      </div>

      <div className="max-h-56 overflow-y-auto space-y-2 pr-1 font-sans text-xs">
        {events.length === 0 ? (
          <div className="text-zinc-500 italic py-2 text-center">暂无实时轨迹事件</div>
        ) : (
          events.map((ev) => (
            <div
              key={`${ev.task_id}-${ev.seq}`}
              className="p-2 rounded bg-zinc-900/70 border border-zinc-800/80 flex flex-col gap-1"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-zinc-500 font-mono text-[10px]">#{ev.seq}</span>
                  {getKindBadge(ev.kind)}
                </div>
                <span className="text-[10px] text-zinc-500 font-mono">
                  {new Date(ev.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-zinc-200 text-xs pl-0.5 leading-relaxed">{ev.human_readable}</p>
              {Object.keys(ev.payload).length > 0 && (
                <div className="text-[10px] text-zinc-400 font-mono bg-black/40 px-2 py-1 rounded border border-zinc-800/50 mt-0.5 overflow-x-auto">
                  {JSON.stringify(ev.payload)}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
