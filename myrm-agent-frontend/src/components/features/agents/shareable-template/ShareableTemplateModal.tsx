import React, { useState } from 'react';
import {
  Share2,
  ShieldCheck,
  Copy,
  Check,
  X,
  Key,
  Bot,
  ExternalLink,
  Layers,
} from 'lucide-react';
import { useShareableTemplateStore } from './useShareableTemplateStore';

export const ShareableTemplateModal: React.FC = () => {
  const { isShareModalOpen, activeTemplate, scrubbingAudit, publishedUrl, closeShareModal } =
    useShareableTemplateStore();
  const [copied, setCopied] = useState<boolean>(false);

  if (!isShareModalOpen || !activeTemplate) {
    return null;
  }

  const handleCopyLink = async (): Promise<void> => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(publishedUrl);
        setCopied(true);
        setTimeout(() => {
          setCopied(false);
        }, 2000);
      }
    } catch {
      // 容错处理降级
    }
  };

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="share-template-title"
      className="fixed inset-0 z-50 flex items-center justify-center w-full h-full p-4 bg-black/60 backdrop-blur-sm"
    >
      <section
        role="document"
        className="w-full max-w-lg overflow-hidden border rounded-xl shadow-2xl bg-slate-900 border-slate-800 text-slate-100 animate-in fade-in zoom-in-95 duration-150"
      >
        <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800/80 bg-slate-950/40">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
              <Share2 className="w-5 h-5" />
            </div>
            <div>
              <h2 id="share-template-title" className="text-base font-semibold leading-tight text-white">
                分享智能体模板
              </h2>
              <p className="text-xs text-slate-400">公开分发链接与自动化安全脱敏审计</p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeShareModal}
            className="p-1.5 transition-colors rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
            aria-label="关闭分享窗口"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="p-6 space-y-5">
          {/* 模板基本信息卡片 */}
          <div className="p-4 border rounded-lg bg-slate-950/60 border-slate-800/80">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
                <Bot className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-medium text-white truncate">{activeTemplate.title}</h3>
                  <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-800 text-slate-300 border border-slate-700">
                    {activeTemplate.baseModel}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400 line-clamp-2">
                  {activeTemplate.description || '无详细描述'}
                </p>
                {activeTemplate.requiredSkills.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 mt-3">
                    <span className="text-[11px] text-slate-500 flex items-center gap-1">
                      <Layers className="w-3 h-3" /> 所需技能:
                    </span>
                    {activeTemplate.requiredSkills.map((skill) => (
                      <span
                        key={skill}
                        className="px-2 py-0.5 text-[10px] rounded-full bg-slate-800 text-sky-300 border border-sky-900/50"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 安全脱敏审计徽章与清单 */}
          <div className="p-4 border rounded-lg bg-emerald-950/20 border-emerald-500/20">
            <div className="flex items-center gap-2 text-emerald-400">
              <ShieldCheck className="w-4 h-4" />
              <span className="text-xs font-semibold">自动化安全脱敏合格 (Zero-Leak)</span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              已将私有凭据与 API Key 擦除并自动转换为运行时安全变量槽位。
            </p>

            {scrubbingAudit && scrubbingAudit.scrubbedKeysCount > 0 ? (
              <div className="mt-3 space-y-1.5">
                <div className="text-[11px] text-slate-400">
                  已剥离私有密钥字段 ({scrubbingAudit.scrubbedKeysCount} 个):
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {activeTemplate.environmentKeySlots.map((slot) => (
                    <span
                      key={slot}
                      className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-mono rounded bg-emerald-900/40 text-emerald-300 border border-emerald-700/40"
                    >
                      <Key className="w-3 h-3" />
                      {slot}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mt-2 text-[11px] text-slate-400 flex items-center gap-1">
                <Check className="w-3 h-3 text-emerald-400" /> 未检测到硬编码机密，可安全分享。
              </div>
            )}
          </div>

          {/* 公开链接分享条 */}
          <div className="space-y-1.5">
            <label htmlFor="share-template-url" className="text-xs font-medium text-slate-300">
              公开模板链接
            </label>
            <div className="flex items-center gap-2">
              <input
                id="share-template-url"
                type="text"
                readOnly
                value={publishedUrl}
                className="flex-1 px-3 py-2 text-xs font-mono border rounded-lg bg-slate-950 border-slate-800 text-slate-300 focus:outline-none focus:border-sky-500"
              />
              <button
                type="button"
                onClick={handleCopyLink}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border rounded-lg bg-sky-600 hover:bg-sky-500 text-white border-sky-500 shrink-0"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-300" />
                    <span>已复制</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>复制链接</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        <footer className="flex items-center justify-between px-6 py-3.5 border-t border-slate-800/80 bg-slate-950/30">
          <span className="text-[11px] text-slate-500 flex items-center gap-1">
            <ExternalLink className="w-3 h-3" /> 他人点击链接即可一键克隆到本地工作区
          </span>
          <button
            type="button"
            onClick={closeShareModal}
            className="px-3.5 py-1.5 text-xs font-medium transition-colors border rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700"
          >
            完成
          </button>
        </footer>
      </section>
    </dialog>
  );
};
