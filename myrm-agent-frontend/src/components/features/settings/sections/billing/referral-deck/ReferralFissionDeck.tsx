import React, { useState } from 'react';
import {
  Share2,
  Gift,
  ShieldCheck,
  Copy,
  Check,
  TrendingUp,
  DollarSign,
  Users,
  Sparkles,
  AlertCircle,
  RotateCcw,
  Edit3,
  CheckCircle2,
} from 'lucide-react';
import { useReferralFissionStore } from './useReferralFissionStore';
import { ReferralShareCardPreview } from './ReferralShareCardPreview';

export const ReferralFissionDeck: React.FC = () => {
  const {
    profile,
    ledger,
    records,
    riskAudit,
    isEditingSlug,
    copiedNoticeVisible,
    updateCustomSlug,
    resetToRandomSlug,
    setEditingSlug,
    triggerCopyNotice,
    dismissNotice,
  } = useReferralFissionStore();

  const [inputSlug, setInputSlug] = useState<string>(profile.slug);
  const [errorMessage, setErrorMessage] = useState<string>('');

  const referralUrl = `https://myrmagent.ai/r/${profile.slug}`;

  const handleCopyLink = async (): Promise<void> => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(referralUrl);
        triggerCopyNotice();
        setTimeout(() => {
          dismissNotice();
        }, 2000);
      }
    } catch {
      // 容错降级
    }
  };

  const handleSaveSlug = (e: React.FormEvent): void => {
    e.preventDefault();
    setErrorMessage('');
    const result = updateCustomSlug(inputSlug);
    if (!result.isValid) {
      setErrorMessage(result.reason ?? 'Slug 不合规');
    }
  };

  return (
    <section
      aria-label="双向算力赠金裂变与 Zero-Dox 推荐看板"
      className="space-y-6 text-slate-100"
    >
      {/* 顶部标题区 */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 border rounded-xl bg-slate-900/60 border-slate-800">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Share2 className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-white">双向算力裂变与增长看板</h3>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <ShieldCheck className="w-3 h-3" /> Zero-Dox 认证
            </span>
          </div>
          <p className="text-xs text-slate-400">
            受邀伙伴享 ${ledger.inviteeDiscountUsd} 礼包，您享 ${ledger.rewardPerInviteUsd} 算力及 10% 云端沙箱包月返佣。
          </p>
        </div>

        {/* 专属短链与一键复制 */}
        <div className="flex items-center gap-2">
          <div className="px-3 py-1.5 text-xs font-mono border rounded-lg bg-slate-950 border-slate-800 text-sky-300">
            {referralUrl}
          </div>
          <button
            type="button"
            onClick={handleCopyLink}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors border rounded-lg bg-sky-600 hover:bg-sky-500 text-white border-sky-500 shrink-0"
          >
            {copiedNoticeVisible ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-300" />
                <span>已复制</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>复制短链</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* 自定义伪名 Slug 治理与防开盒说明 */}
      <div className="p-4 border rounded-xl bg-slate-900/40 border-slate-800/80 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-300">个性化伪名短码 (Pseudonymous Slug)</span>
            {profile.isCustomSlug ? (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800">自定义</span>
            ) : (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">CSPRNG 随机</span>
            )}
          </div>
          {!isEditingSlug ? (
            <button
              type="button"
              onClick={() => {
                setInputSlug(profile.slug);
                setEditingSlug(true);
              }}
              className="inline-flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 transition-colors"
            >
              <Edit3 className="w-3 h-3" /> 修改个性短码
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setEditingSlug(false);
                setErrorMessage('');
              }}
              className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              取消
            </button>
          )}
        </div>

        {isEditingSlug ? (
          <form onSubmit={handleSaveSlug} className="space-y-2 pt-2 border-t border-slate-800/60">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400 font-mono">myrmagent.ai/r/</span>
              <input
                type="text"
                value={inputSlug}
                onChange={(e) => setInputSlug(e.target.value)}
                placeholder="例如: coder-bob"
                className="flex-1 px-3 py-1.5 text-xs font-mono border rounded-lg bg-slate-950 border-slate-800 text-white focus:outline-none focus:border-sky-500"
              />
              <button
                type="submit"
                className="px-3 py-1.5 text-xs font-medium border rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500"
              >
                保存
              </button>
              <button
                type="button"
                onClick={resetToRandomSlug}
                className="p-1.5 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700"
                title="重置为随机无语义短码"
                aria-label="重置为随机无语义短码"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>
            {errorMessage ? (
              <p className="text-xs text-rose-400 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {errorMessage}
              </p>
            ) : (
              <p className="text-[11px] text-slate-400">
                遵循 Zero-Dox 隐私红线：严禁包含您的真实全名拼音、邮箱或敏感身份信息。
              </p>
            )}
          </form>
        ) : (
          <p className="text-xs text-slate-400 leading-relaxed">
            系统默认生成安全加密随机数（CSPRNG）无语义短码，杜绝社交媒体分享时因暴露姓名遭人肉开盒。
          </p>
        )}
      </div>

      {/* 算力账本 4 维核心数据仪表盘 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="p-4 border rounded-xl bg-slate-950/60 border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>累计裂变收益</span>
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-xl font-bold text-white font-mono">
            ${ledger.totalEarnedUsd}
          </div>
          <div className="mt-1 text-[11px] text-emerald-400 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> 可抵扣全平台模型
          </div>
        </div>

        <div className="p-4 border rounded-xl bg-slate-950/60 border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>当前可用额度</span>
            <Sparkles className="w-4 h-4 text-sky-400" />
          </div>
          <div className="mt-2 text-xl font-bold text-sky-300 font-mono">
            ${ledger.availableBalanceUsd}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            算力实时生效
          </div>
        </div>

        <div className="p-4 border rounded-xl bg-slate-950/60 border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>云端沙箱分润</span>
            <Gift className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="mt-2 text-xl font-bold text-white font-mono">
            ${ledger.totalCloudKickbackUsd}
          </div>
          <div className="mt-1 text-[11px] text-indigo-400">
            10% 持续包月返佣
          </div>
        </div>

        <div className="p-4 border rounded-xl bg-slate-950/60 border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>成功邀请总数</span>
            <Users className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2 text-xl font-bold text-white font-mono">
            {ledger.totalInvitedCount} <span className="text-xs font-normal text-slate-400">位极客</span>
          </div>
          <div className="mt-1 text-[11px] text-amber-400">
            {ledger.activeCloudSubscribersCount} 人常驻云端
          </div>
        </div>
      </div>

      {/* 卡片预览与风控双栏 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
        <ReferralShareCardPreview />

        {/* 防刷风控指纹门禁卡片 */}
        <div className="p-5 border rounded-xl bg-slate-900/40 border-slate-800 space-y-3.5">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-white flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-400" /> 防刷反作弊风控门禁 (Anti-Sybil)
            </h4>
            <span className="px-2 py-0.5 text-[10px] rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
              正常健康
            </span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            系统采用浏览器 Canvas 熵、设备指纹及 IP 子网综合审计，杜绝黑产批量小号刷取赠金，保障真实极客创作者利益。
          </p>

          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">设备指纹一致性:</span>
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> 已通过
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Canvas 熵审计:</span>
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> 无异常
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">子网风险评分:</span>
              <span className="font-mono text-slate-200">{riskAudit.subnetRiskScore} / 100 (低风险)</span>
            </div>
          </div>
        </div>
      </div>

      {/* 收益流水明细列表 */}
      <div className="p-5 border rounded-xl bg-slate-900/60 border-slate-800 space-y-3.5">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-white">算力收益流水账本</h4>
          <span className="text-xs text-slate-400">显示最近收益记录</span>
        </div>

        <div className="divide-y divide-slate-800/80">
          {records.map((rec) => (
            <div key={rec.id} className="py-3 flex items-center justify-between text-xs">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sky-400 font-medium">@{rec.inviteePseudonym}</span>
                  <span className="text-slate-300">{rec.note}</span>
                </div>
                <div className="text-[10px] text-slate-500 font-mono">
                  {new Date(rec.timestamp).toLocaleString()}
                </div>
              </div>
              <div className="font-mono text-sm font-bold text-emerald-400">
                +${rec.amountUsd}.00
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
