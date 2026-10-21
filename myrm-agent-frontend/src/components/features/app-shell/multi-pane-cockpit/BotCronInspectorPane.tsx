import React from 'react';
import { Clock, CheckCircle2, AlertCircle, Loader2, X, Plus, Calendar } from 'lucide-react';
import { useMultiPaneCockpitStore } from './useMultiPaneCockpitStore';

export const BotCronInspectorPane: React.FC = () => {
  const {
    selectedBotId,
    bots,
    isCronInspectorOpen,
    toggleCronInspector,
    toggleBotCronJob,
  } = useMultiPaneCockpitStore();

  const currentBot = bots.find((b) => b.id === selectedBotId);

  if (!isCronInspectorOpen || !currentBot) {
    return null;
  }

  return (
    <aside
      aria-label="Bot 定时任务监控面板"
      className="flex w-80 flex-col border-l border-slate-800 bg-slate-900/95 transition-all duration-200"
    >
      <div className="flex h-12 items-center justify-between border-b border-slate-800 px-3.5">
        <div className="flex items-center space-x-2">
          <Calendar className="h-4 w-4 text-amber-400" />
          <span className="text-xs font-semibold text-slate-100">
            {currentBot.name} · 定时任务
          </span>
          <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
            {currentBot.cronJobs.length} 项
          </span>
        </div>
        <button
          type="button"
          onClick={() => {
            toggleCronInspector(false);
          }}
          className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          aria-label="收起定时监控栏"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>专属调度列表</span>
          <button
            type="button"
            className="inline-flex items-center space-x-1 text-[11px] text-blue-400 hover:text-blue-300"
          >
            <Plus className="h-3 w-3" />
            <span>新建 Cron</span>
          </button>
        </div>

        {currentBot.cronJobs.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-800 p-4 text-center text-xs text-slate-400">
            该智能体暂未绑定定时自动任务
          </div>
        ) : (
          currentBot.cronJobs.map((job) => {
            return (
              <div
                key={job.id}
                className={`rounded-lg border p-3 transition-colors ${
                  job.isEnabled
                    ? 'border-slate-700 bg-slate-850/80'
                    : 'border-slate-800/80 bg-slate-900/40 opacity-70'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="text-xs font-semibold text-slate-200">{job.title}</h4>
                    <div className="mt-1 flex items-center space-x-2 text-[11px] text-slate-400">
                      <Clock className="h-3 w-3 text-slate-400" />
                      <span className="font-mono text-slate-300">{job.cronExpression}</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      toggleBotCronJob(currentBot.id, job.id, !job.isEnabled);
                    }}
                    role="switch"
                    aria-checked={job.isEnabled}
                    aria-label={`切换 ${job.title} 定时开关`}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                      job.isEnabled ? 'bg-amber-500' : 'bg-slate-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 ease-in-out ${
                        job.isEnabled ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>

                <div className="mt-2.5 flex items-center justify-between border-t border-slate-800/80 pt-2 text-[10px] text-slate-400">
                  <span>上次执行: {job.lastRunTime ?? '尚未执行'}</span>
                  {job.lastStatus === 'success' && (
                    <span className="inline-flex items-center space-x-1 text-emerald-400">
                      <CheckCircle2 className="h-3 w-3" />
                      <span>执行成功</span>
                    </span>
                  )}
                  {job.lastStatus === 'running' && (
                    <span className="inline-flex items-center space-x-1 text-blue-400">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      <span>正在执行</span>
                    </span>
                  )}
                  {job.lastStatus === 'failed' && (
                    <span className="inline-flex items-center space-x-1 text-rose-400">
                      <AlertCircle className="h-3 w-3" />
                      <span>执行异常</span>
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {currentBot.latestOutputSummary && (
        <div className="border-t border-slate-800 p-3">
          <div className="text-[11px] font-medium text-slate-400 mb-1">最近一次运行产物摘要</div>
          <div className="rounded bg-slate-950/80 p-2 text-[11px] text-slate-300 border border-slate-800">
            {currentBot.latestOutputSummary}
          </div>
        </div>
      )}
    </aside>
  );
};
