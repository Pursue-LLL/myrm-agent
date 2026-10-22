import React, { useState } from 'react';
import {
  AlertCircle,
  Wrench,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  X,
  Loader2,
  Sparkles,
  Shield,
  Layers,
} from 'lucide-react';
import { useStderrDiagnosticStore } from './useStderrDiagnosticStore';

export const ActionableDiagnosticSurfaceCard: React.FC = () => {
  const {
    activeDiagnostic,
    isFixing,
    fixSuccessMessage,
    executeFixAction,
    dismissDiagnostic,
  } = useStderrDiagnosticStore();

  const [isRawSnippetOpen, setIsRawSnippetOpen] = useState(false);

  if (!activeDiagnostic) {
    return null;
  }

  return (
    <section
      aria-label="进程退出因果诊断与可操作排障向导"
      className="relative my-3 w-full rounded-xl border border-rose-500/30 bg-slate-900/95 p-4 shadow-xl backdrop-blur-md transition-all"
    >
      {/* 顶部标题栏 */}
      <div className="flex items-start justify-between border-b border-slate-800 pb-3">
        <div className="flex items-start space-x-2.5">
          <div className="rounded-lg bg-rose-500/10 p-2 text-rose-400">
            <AlertCircle className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-xs font-semibold text-slate-100">
                {activeDiagnostic.categoryLabel}
              </h3>
              <span className="rounded bg-rose-500/20 px-2 py-0.5 font-mono text-[10px] font-medium text-rose-300">
                Exit Code {activeDiagnostic.exitCode}
              </span>
              <span className="inline-flex items-center space-x-1 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
                <Shield className="h-3 w-3 text-emerald-400" />
                <span>敏感路径与令牌已脱敏</span>
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-300 leading-relaxed">
              {activeDiagnostic.rootCauseSummary}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={dismissDiagnostic}
          className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          aria-label="关闭诊断卡片"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 修复成功反馈条 */}
      {fixSuccessMessage && (
        <div className="mt-3 flex items-center space-x-2 rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-2.5 text-xs text-emerald-300">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          <span>{fixSuccessMessage}</span>
        </div>
      )}

      {/* 可操作修复向导操作区 */}
      <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {activeDiagnostic.fixGuides.map((guide) => (
            <button
              key={guide.actionId}
              type="button"
              disabled={isFixing}
              onClick={() => {
                void executeFixAction(guide.actionId);
              }}
              className={`inline-flex items-center space-x-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                guide.isRecommended
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20 hover:bg-blue-500 disabled:opacity-50'
                  : 'border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-50'
              }`}
            >
              {isFixing ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>执行修复中...</span>
                </>
              ) : (
                <>
                  {guide.isRecommended ? (
                    <Sparkles className="h-3.5 w-3.5 text-amber-300" />
                  ) : (
                    <Wrench className="h-3.5 w-3.5 text-slate-400" />
                  )}
                  <span>{guide.buttonLabel}</span>
                </>
              )}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => {
            setIsRawSnippetOpen(!isRawSnippetOpen);
          }}
          className="inline-flex items-center space-x-1 text-[11px] text-slate-400 hover:text-slate-200"
          aria-expanded={isRawSnippetOpen}
          aria-label="展开或收起受限脱敏 Stderr 尾部"
        >
          <Layers className="h-3 w-3" />
          <span>查看受限 2KiB 诊断尾部</span>
          {isRawSnippetOpen ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      {/* 脱敏 Stderr 代码块折叠面板 */}
      {isRawSnippetOpen && (
        <div className="mt-3 overflow-hidden rounded-lg border border-slate-800 bg-slate-950 p-3">
          <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1.5">
            <span>TERMINAL STDERR BOUNDED TAIL (MAX 2 KiB)</span>
            <span>置信度: {(activeDiagnostic.confidenceScore * 100).toFixed(0)}%</span>
          </div>
          <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] text-slate-300 leading-tight">
            {activeDiagnostic.sanitizedStderrSnippet}
          </pre>
        </div>
      )}
    </section>
  );
};
