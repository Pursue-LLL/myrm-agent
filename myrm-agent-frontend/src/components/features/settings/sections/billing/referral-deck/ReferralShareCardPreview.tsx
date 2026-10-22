import React from 'react';
import { Gift, ShieldCheck, Sparkles, QrCode, ArrowUpRight } from 'lucide-react';
import { useReferralFissionStore } from './useReferralFissionStore';

export const ReferralShareCardPreview: React.FC = () => {
  const { profile, ledger } = useReferralFissionStore();
  const referralUrl = `https://myrmagent.ai/r/${profile.slug}`;

  return (
    <article
      aria-label="受邀者社交卡片预览"
      className="overflow-hidden border rounded-xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-indigo-950/40 border-slate-800 shadow-xl"
    >
      <div className="p-5 space-y-4">
        {/* 卡片顶部标签 */}
        <div className="flex items-center justify-between">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <Gift className="w-3.5 h-3.5" />
            <span>新用户专属赠金</span>
          </div>
          <div className="inline-flex items-center gap-1 text-[11px] text-sky-400">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Zero-Dox 匿名保护</span>
          </div>
        </div>

        {/* 核心权益标题 */}
        <div>
          <h4 className="text-base font-bold text-white flex items-center gap-1.5">
            <span>立减 ${ledger.inviteeDiscountUsd} 美元云端算力礼包</span>
            <Sparkles className="w-4 h-4 text-amber-400" />
          </h4>
          <p className="mt-1 text-xs text-slate-300 leading-relaxed">
            来自匿名极客专属邀请。注册即刻开通高性能沙箱环境，畅享 DeepSeek-V3 与 Claude-3.5 算力额度。
          </p>
        </div>

        {/* 专属匿名邀请码展示条 */}
        <div className="p-3 border rounded-lg bg-slate-950/80 border-slate-800 flex items-center justify-between">
          <div className="space-y-0.5">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-mono">
              专属裂变口令
            </span>
            <span className="font-mono text-xs font-semibold text-sky-300">
              {profile.slug}
            </span>
          </div>
          <div className="p-1.5 rounded-md bg-slate-800 text-slate-400 border border-slate-700">
            <QrCode className="w-4 h-4" />
          </div>
        </div>

        {/* 卡片底栏信息 */}
        <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 text-[11px] text-slate-400">
          <span className="font-mono truncate max-w-[200px]">{referralUrl}</span>
          <span className="flex items-center gap-0.5 text-slate-300 hover:text-white">
            <span>点击预览</span>
            <ArrowUpRight className="w-3 h-3" />
          </span>
        </div>
      </div>
    </article>
  );
};
