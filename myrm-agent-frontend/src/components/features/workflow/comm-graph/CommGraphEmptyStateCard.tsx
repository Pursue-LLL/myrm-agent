import React from 'react';
import { Network, Loader2, Sparkles, PlusCircle } from 'lucide-react';
import { useCommGraphStore } from './useCommGraphStore';

export const CommGraphEmptyStateCard: React.FC = () => {
  const { isPipelineInitializing, addCommEvent } = useCommGraphStore();

  const handleSeedFirstEvent = () => {
    addCommEvent({
      stepIndex: 1,
      fromAgent: 'CoordinatorAgent (协调总管)',
      toAgent: 'ArchitectAgent (架构师)',
      action: 'dispatch_subtask',
      payloadSummary: '下发任务: 拆解分布式通讯拓扑与事件流路由方案',
      status: 'completed',
      latencyMs: 42,
    });
  };

  return (
    <output
      aria-live="polite"
      className="block flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-700/80 bg-slate-900/40 p-8 text-center text-slate-300"
    >
      <div className="relative mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
        <Network className="h-6 w-6" />
        {isPipelineInitializing && (
          <span className="absolute -top-1 -right-1 flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-indigo-500" />
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
        {isPipelineInitializing ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
            <span>正在建立多智能体全双工协同链路...</span>
          </>
        ) : (
          <span>暂无协同事件 (No events yet)</span>
        )}
      </div>

      <p className="mt-2 max-w-sm text-xs text-slate-400 leading-relaxed">
        协同时间轴目前为空。误导性的 Live 实时徽标已自动隐藏，等待 Agent 间首次产生通讯事件后自动激活。
      </p>

      <div className="mt-5 flex items-center gap-3">
        <button
          type="button"
          onClick={handleSeedFirstEvent}
          className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/30 bg-indigo-600/20 px-3.5 py-2 text-xs font-semibold text-indigo-300 shadow-sm hover:bg-indigo-600/30 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <PlusCircle className="h-3.5 w-3.5" />
          模拟触发第一轮协同通讯
        </button>
      </div>

      <div className="mt-4 flex items-center gap-1 text-[11px] text-slate-400">
        <Sparkles className="h-3 w-3 text-indigo-400" />
        <span>支持回溯历史游标并在切回最新时双向原位保持</span>
      </div>
    </output>
  );
};
