import React, { useState } from 'react';
import {
  Sparkles,
  Check,
  X,
  Zap,
  ArrowRight,
  Clock,
  Loader2,
} from 'lucide-react';
import { useWorkbenchStore } from './useWorkbenchStore';

export const InPlacePartialRefinementPopover: React.FC = () => {
  const {
    currentSelection,
    refinementStatus,
    currentRefinementTask,
    startRefinement,
    applyRefinement,
    rejectRefinement,
  } = useWorkbenchStore();

  const [instruction, setInstruction] = useState('');

  if (
    !currentSelection ||
    !['prompting', 'refining', 'previewing'].includes(refinementStatus)
  ) {
    return null;
  }

  const isRefining = refinementStatus === 'refining';
  const isPreviewing = refinementStatus === 'previewing';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!instruction.trim() || isRefining) {
      return;
    }
    await startRefinement(instruction);
  };

  return (
    <aside
      aria-label="划选就地局部重构编辑卡"
      className="fixed bottom-6 right-6 z-40 w-96 max-w-[calc(100vw-3rem)] bg-slate-900 border border-indigo-500/50 rounded-xl shadow-2xl p-4 text-slate-100 flex flex-col space-y-3 backdrop-blur-md transition-all"
      data-testid="in-place-partial-refinement-popover"
    >
      {/* 头部微提示与选区摘要 */}
      <header className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <div className="p-1.5 rounded-md bg-indigo-600/30 text-indigo-400 border border-indigo-500/40">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white">划选就地重构精修</h4>
            <span className="text-[10px] text-slate-400">
              免全篇重写 · 仅派发选中 Chunk · 秒级替换
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={rejectRefinement}
          aria-label="取消局部编辑"
          className="p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </header>

      {/* 选中的原始内容片段 */}
      <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-300 font-mono truncate max-h-16 overflow-hidden">
        <span className="text-slate-500 mr-1 select-none">选区:</span>
        {currentSelection.selectedText}
      </div>

      {/* 指令输入表单 */}
      {!isPreviewing && (
        <form onSubmit={handleSubmit} className="space-y-2">
          <label htmlFor="refinement-instruction-input" className="sr-only">
            输入就地精修指令
          </label>
          <textarea
            id="refinement-instruction-input"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            disabled={isRefining}
            rows={2}
            placeholder="输入针对选中区域的微调指令，如：改为保守估值，补充汇率风险..."
            className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none font-sans"
          />

          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] text-emerald-400 flex items-center space-x-1">
              <Zap className="w-3 h-3" />
              <span>预计节省 90%+ Token</span>
            </span>

            <button
              type="submit"
              disabled={isRefining || !instruction.trim()}
              aria-label="提交局部重构"
              className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white rounded-md flex items-center space-x-1.5 transition-all shadow"
            >
              {isRefining ? (
                <>
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>重构中...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3 h-3" />
                  <span>就地精修</span>
                </>
              )}
            </button>
          </div>
        </form>
      )}

      {/* 差量对比与确认预览区 */}
      {isPreviewing && currentRefinementTask && (
        <div className="space-y-3 pt-1" data-testid="refinement-preview-section">
          {/* 性能与节约统计条 */}
          <div className="flex items-center justify-between text-[10px] bg-slate-950 px-2 py-1.5 rounded border border-slate-800">
            <span className="text-emerald-400 font-semibold flex items-center space-x-1">
              <Zap className="w-3 h-3" />
              <span>
                节省 {currentRefinementTask.tokenSavingsPercent}% 算力 Token
              </span>
            </span>
            <span className="text-slate-400 flex items-center space-x-1">
              <Clock className="w-3 h-3" />
              <span>时延 1.8s (免全篇重写)</span>
            </span>
          </div>

          {/* 生成结果预览 */}
          <div className="p-2.5 rounded bg-slate-950/90 border border-emerald-900/60 text-xs text-emerald-200 font-sans max-h-32 overflow-y-auto space-y-1">
            <div className="text-[10px] text-emerald-400/80 font-mono font-semibold">
              替换预览 (Diff Preview):
            </div>
            <pre className="text-[11px] whitespace-pre-wrap font-sans">
              {currentRefinementTask.refinedChunk}
            </pre>
          </div>

          {/* 操作按钮区 */}
          <div className="flex items-center justify-end space-x-2 pt-1 border-t border-slate-800">
            <button
              type="button"
              onClick={rejectRefinement}
              aria-label="舍弃本次重构"
              className="px-2.5 py-1 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
            >
              放弃
            </button>
            <button
              type="button"
              onClick={applyRefinement}
              aria-label="采纳就地替换"
              className="px-3.5 py-1 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-md flex items-center space-x-1.5 shadow transition-all"
            >
              <Check className="w-3.5 h-3.5" />
              <span>采纳并原子替换</span>
            </button>
          </div>
        </div>
      )}
    </aside>
  );
};
