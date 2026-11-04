import React from 'react';
import {
  X,
  ShieldAlert,
  Scale,
  CheckCircle2,
  ArrowRight,
  Gavel,
} from 'lucide-react';
import { useTeamRuntimeStore } from './useTeamRuntimeStore';

export const ConflictResolutionModal: React.FC = () => {
  const {
    activeConflictId,
    conflicts,
    closeConflictModal,
    arbitrateConflict,
  } = useTeamRuntimeStore();

  const conflict = conflicts.find((c) => c.id === activeConflictId);

  if (!conflict) {
    return null;
  }

  const isResolved = conflict.status === 'resolved';

  return (
    <dialog
      open
      aria-label="数字团队不可调和矛盾仲裁卡片"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm border-none w-full h-full max-w-none max-h-none m-0"
    >
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-amber-500/40 bg-slate-900 shadow-2xl overflow-hidden">
        {/* Header */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 px-6 bg-amber-950/20">
          <div className="flex items-center space-x-2.5">
            <div className="rounded-lg bg-amber-500/10 p-2 text-amber-400">
              <ShieldAlert className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-xs font-semibold text-slate-100 flex items-center space-x-2">
                <span>{conflict.title}</span>
                <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-medium text-amber-300">
                  人类拍板仲裁
                </span>
              </h2>
              <p className="text-[11px] text-slate-400">
                模型已拒绝自行编造折中案，将关键业务约束权衡交由指挥官定夺
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeConflictModal}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            aria-label="关闭仲裁卡片"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          <div className="rounded-lg border border-amber-500/20 bg-amber-950/10 p-3.5 text-xs text-amber-200">
            <div className="flex items-center space-x-1.5 font-semibold mb-1 text-amber-300">
              <Scale className="h-4 w-4" />
              <span>不可调和的矛盾根因：</span>
            </div>
            <p className="text-slate-300 leading-relaxed">
              {conflict.conflictDescription}
            </p>
          </div>

          <div className="space-y-3">
            <div className="text-xs font-semibold text-slate-200">
              请选择您的裁决基线（团队将立即以此基线统一收口）：
            </div>

            <div className="grid grid-cols-1 gap-3">
              {conflict.options.map((option) => {
                const isSelected = conflict.selectedOptionId === option.id;

                return (
                  <div
                    key={option.id}
                    className={`rounded-xl border p-4 transition-all ${
                      isSelected
                        ? 'border-emerald-500 bg-emerald-950/20 shadow-sm'
                        : 'border-slate-800 bg-slate-850/80 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 pr-3">
                        <div className="flex items-center space-x-2">
                          <h4 className="text-xs font-semibold text-slate-100">
                            {option.title}
                          </h4>
                          {isSelected && (
                            <span className="inline-flex items-center space-x-1 rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-300">
                              <CheckCircle2 className="h-3 w-3" />
                              <span>已采纳为法定基准</span>
                            </span>
                          )}
                        </div>
                        <p className="mt-1.5 text-[11px] text-slate-300">
                          <span className="text-slate-400">影响分析: </span>
                          {option.impactAnalysis}
                        </p>
                        <p className="mt-1 text-[11px] text-emerald-400">
                          <span className="text-slate-400">调度指令: </span>
                          {option.actionDirective}
                        </p>
                      </div>

                      {!isResolved && (
                        <button
                          type="button"
                          onClick={() => {
                            arbitrateConflict(conflict.id, option.id);
                          }}
                          className="inline-flex shrink-0 items-center space-x-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow hover:bg-blue-500"
                        >
                          <Gavel className="h-3.5 w-3.5" />
                          <span>拍板此方案</span>
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="flex h-12 shrink-0 items-center justify-between border-t border-slate-800 px-6 bg-slate-950/60 text-[11px] text-slate-400">
          <span>仲裁结果将固化为团队决议并写入交付契约已决事实列表</span>
          <button
            type="button"
            onClick={closeConflictModal}
            className="rounded px-3 py-1 text-slate-300 hover:bg-slate-800"
          >
            {isResolved ? '完成并关闭' : '暂缓裁决'}
          </button>
        </footer>
      </div>
    </dialog>
  );
};
