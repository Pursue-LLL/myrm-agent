import React, { useState } from 'react';
import {
  Share2,
  X,
  Copy,
  Check,
  Clock,
  Shield,
  Ban,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { useVisualArtifactStudioStore } from './useVisualArtifactStudioStore';
import type { PublicShareRecord } from './designSpecTypes';

export const PublicShareModal: React.FC = () => {
  const {
    isShareModalOpen,
    currentArtifactId,
    publicShares,
    closeShareModal,
    generatePublicShare,
    revokePublicShare,
  } = useVisualArtifactStudioStore();

  const [durationHours, setDurationHours] = useState<number | null>(24);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (!isShareModalOpen) {
    return null;
  }

  const activeShares = publicShares.filter(
    (s) => s.artifactId === currentArtifactId
  );

  const handleCreateShare = () => {
    generatePublicShare(currentArtifactId, durationHours);
  };

  const handleCopyLink = async (record: PublicShareRecord) => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(record.publicUrl);
      }
      setCopiedId(record.shareId);
      setTimeout(() => {
        setCopiedId(null);
      }, 2000);
    } catch {
      // 容错处理
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <dialog
        open
        aria-label="零配置一键公网发布弹窗"
        className="relative w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 p-6 text-slate-100 shadow-2xl overflow-hidden m-0"
      >
        {/* 弹窗头部 */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
              <Share2 className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                零配置一键公网安全发布
              </h2>
              <p className="text-xs text-slate-400">
                无需服务器与域名，秒级生成独立访问短链
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeShareModal}
            aria-label="关闭公网发布弹窗"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 配置区 */}
        <div className="mt-4 space-y-4">
          <div>
            <span className="block text-xs font-semibold text-slate-300 mb-1.5">
              安全链接有效时长
            </span>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: '24 小时临时', value: 24 },
                { label: '7 天安全展示', value: 168 },
                { label: '永久有效', value: null },
              ].map((opt) => (
                <button
                  key={String(opt.value)}
                  type="button"
                  onClick={() => {
                    setDurationHours(opt.value);
                  }}
                  className={`rounded-lg border p-2 text-center text-xs font-medium transition-all ${
                    durationHours === opt.value
                      ? 'border-indigo-500 bg-indigo-600/20 text-indigo-300 shadow-sm'
                      : 'border-slate-800 bg-slate-800/40 text-slate-400 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-center gap-1">
                    <Clock className="h-3 w-3" />
                    <span>{opt.label}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-800/30 p-3 text-xs text-slate-400 space-y-1.5">
            <div className="flex items-center gap-1.5 text-slate-300 font-medium">
              <Shield className="h-3.5 w-3.5 text-emerald-400" />
              <span>自动挂载安全防伪浮标</span>
            </div>
            <p className="text-[11px] leading-relaxed">
              发布的应用右下角将附带 “由 Myrmidon AI 遵循 DESIGN.md 规范自动构建” 签名水印，支持随时一键撤销访问。
            </p>
          </div>

          <button
            type="button"
            onClick={handleCreateShare}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 text-xs font-semibold text-white shadow-md hover:bg-indigo-500 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <Sparkles className="h-3.5 w-3.5" />
            生成新的公网分享链接
          </button>
        </div>

        {/* 历史发布记录 */}
        {activeShares.length > 0 && (
          <div className="mt-5 border-t border-slate-800 pt-4">
            <h3 className="text-xs font-semibold text-slate-300 mb-2.5">
              已生成的分享短链 ({activeShares.length})
            </h3>
            <div className="space-y-2 max-h-40 overflow-y-auto scrollbar-thin">
              {activeShares.map((rec) => (
                <div
                  key={rec.shareId}
                  className={`flex items-center justify-between rounded-lg border p-2.5 text-xs transition-all ${
                    rec.isRevoked
                      ? 'border-slate-800 bg-slate-900/50 opacity-60'
                      : 'border-slate-800 bg-slate-800/50'
                  }`}
                >
                  <div className="min-w-0 flex-1 pr-3">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-indigo-300 truncate">
                        {rec.publicUrl}
                      </span>
                      {rec.isRevoked && (
                        <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] text-rose-400 border border-rose-500/20">
                          已撤销
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      {rec.expiresAt
                        ? `将于 ${new Date(rec.expiresAt).toLocaleDateString()} 到期`
                        : '永久有效'}{' '}
                      • 访问 {rec.visitCount} 次
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {!rec.isRevoked && (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            handleCopyLink(rec);
                          }}
                          aria-label="复制公网短链"
                          className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:text-white transition-colors"
                        >
                          {copiedId === rec.shareId ? (
                            <Check className="h-3.5 w-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <a
                          href={rec.publicUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label="在新窗口打开分享页"
                          className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:text-white transition-colors"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                        <button
                          type="button"
                          onClick={() => {
                            revokePublicShare(rec.shareId);
                          }}
                          aria-label="撤销此短链"
                          className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-1.5 text-rose-400 hover:bg-rose-500/20 transition-colors"
                        >
                          <Ban className="h-3.5 w-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </dialog>
    </div>
  );
};
