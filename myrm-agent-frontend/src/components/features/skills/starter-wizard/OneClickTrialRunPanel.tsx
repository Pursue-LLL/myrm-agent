import React from 'react';
import { Play, Loader2, CheckCircle2, AlertCircle, FileText, Zap } from 'lucide-react';
import type { TrialRunResult } from './starterWizardTypes';

interface OneClickTrialRunPanelProps {
  trialRun: TrialRunResult;
  onExecuteTrialRun: () => void;
  disabled?: boolean;
}

export const OneClickTrialRunPanel: React.FC<OneClickTrialRunPanelProps> = ({
  trialRun,
  onExecuteTrialRun,
  disabled = false,
}) => {
  const isRunning = trialRun.status === 'running';
  const isSuccess = trialRun.status === 'success';
  const isFailed = trialRun.status === 'failed';

  return (
    <div className="space-y-3 rounded-lg border border-slate-700/60 bg-slate-900/60 p-3.5 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-1.5">
          <Zap className="h-4 w-4 text-amber-400" />
          <span className="text-xs font-semibold text-slate-200">即刻单填试跑</span>
          <span className="text-[11px] text-slate-400">（无需复杂提示词，一键校验生成质量）</span>
        </div>
        <button
          type="button"
          onClick={onExecuteTrialRun}
          disabled={disabled || isRunning}
          className="inline-flex items-center space-x-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="立即试跑一次"
        >
          {isRunning ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>提取处理中...</span>
            </>
          ) : (
            <>
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>立即试跑一次</span>
            </>
          )}
        </button>
      </div>

      {isSuccess && trialRun.summaryPreview && (
        <div className="space-y-2 rounded-md border border-emerald-500/30 bg-emerald-950/20 p-3 text-xs text-slate-200">
          <div className="flex items-center justify-between text-emerald-400">
            <span className="inline-flex items-center space-x-1 font-medium">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>试跑成功，产物已就绪</span>
            </span>
            <div className="flex items-center space-x-3 text-[11px] text-slate-400">
              {trialRun.extractedItemsCount !== undefined && (
                <span>提炼要素: {trialRun.extractedItemsCount} 条</span>
              )}
              {trialRun.executionDurationMs !== undefined && (
                <span>耗时: {trialRun.executionDurationMs}ms</span>
              )}
            </div>
          </div>

          <div className="mt-1.5 max-h-48 overflow-y-auto whitespace-pre-wrap rounded bg-slate-950/60 p-2.5 font-mono text-[11px] text-slate-300 border border-slate-800">
            {trialRun.summaryPreview}
          </div>
        </div>
      )}

      {isFailed && (
        <div className="flex items-center space-x-2 rounded-md border border-rose-500/30 bg-rose-950/20 p-2.5 text-xs text-rose-300">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
          <span>{trialRun.errorMessage ?? '试跑过程发生异常，请检查本地环境授权'}</span>
        </div>
      )}

      {trialRun.status === 'idle' && (
        <div className="flex items-center space-x-2 rounded-md border border-dashed border-slate-700/60 p-3 text-[11px] text-slate-400">
          <FileText className="h-4 w-4 text-slate-400" />
          <span>点击上方按钮将根据所选目标与视角进行一次极速试跑，确认符合预期后再开启定时。</span>
        </div>
      )}
    </div>
  );
};
