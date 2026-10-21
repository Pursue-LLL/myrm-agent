import React, { useState } from 'react';
import {
  ListChecks,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
  X,
  Copy,
  Check,
  Clock,
  Sparkles,
} from 'lucide-react';
import { useLongTaskNotifyStore } from './useLongTaskNotifyStore';

export const SourcedResultChecklistModal: React.FC = () => {
  const {
    activeTask,
    isReviewModalOpen,
    closeReviewModal,
  } = useLongTaskNotifyStore();

  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (!isReviewModalOpen || !activeTask) {
    return null;
  }

  const checklist = activeTask.sourcedChecklist;

  const handleCopyLink = async (id: string, url: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      await navigator.clipboard.writeText(url);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />
      <dialog
        open
        aria-labelledby="review-modal-title"
        className="fixed inset-0 z-50 m-auto w-full max-w-2xl bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl p-0 flex flex-col text-slate-100 overflow-hidden"
        data-testid="sourced-result-checklist-modal"
      >
        {/* 头部标题与完成指标 */}
        <header className="px-5 py-4 border-b border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-lg bg-emerald-600/20 text-emerald-400 border border-emerald-500/30">
              <ListChecks className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 id="review-modal-title" className="font-bold text-xs text-white">
                  长任务结果复盘 · 带来源权威清单
                </h3>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/60 font-mono">
                  已核验 {checklist.length} 项
                </span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">
                任务已在云端沙箱自主完成，所有决策结论均追溯至公开白皮书与官方SLA文档
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeReviewModal}
            aria-label="关闭清单复盘窗口"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 核心清单列表区 */}
        <div className="p-5 overflow-y-auto max-h-[420px] space-y-3 text-xs">
          {checklist.map((item) => (
            <div
              key={item.id}
              className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2 hover:border-slate-700 transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span className="font-semibold text-slate-200 text-xs">
                    {item.title}
                  </span>
                </div>

                <div className="flex items-center space-x-1.5 shrink-0">
                  <span className="inline-flex items-center space-x-1 text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/60">
                    <ShieldCheck className="w-2.5 h-2.5" />
                    <span>官方源校验</span>
                  </span>

                  <button
                    type="button"
                    onClick={() => handleCopyLink(item.id, item.sourceUrl)}
                    aria-label={`复制 ${item.title} 来源链接`}
                    className="p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
                  >
                    {copiedId === item.id ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                  </button>
                </div>
              </div>

              {/* 关键摘要引文 */}
              <p className="text-[11px] text-slate-300 leading-relaxed pl-6 border-l-2 border-indigo-500/40 ml-2">
                {item.snippet}
              </p>

              {/* 来源链接与标题 */}
              <div className="pt-1 flex items-center justify-between text-[10px] text-slate-400 pl-2">
                <a
                  href={item.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-400 hover:text-indigo-300 hover:underline flex items-center space-x-1 font-mono truncate max-w-sm"
                >
                  <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                  <span className="truncate">{item.sourceTitle}</span>
                </a>
                <span className="text-slate-500 font-mono">权威出处</span>
              </div>
            </div>
          ))}
        </div>

        {/* 底部关闭与就地应用操作条 */}
        <footer className="px-5 py-3 border-t border-slate-800 bg-slate-950/70 flex items-center justify-between text-xs">
          <div className="text-[11px] text-slate-400 flex items-center space-x-1">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>可直接将清单条目一键导入会话上下文或导出报告</span>
          </div>

          <button
            type="button"
            onClick={closeReviewModal}
            className="px-4 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded transition-colors"
          >
            完成复盘
          </button>
        </footer>
      </dialog>
    </>
  );
};
