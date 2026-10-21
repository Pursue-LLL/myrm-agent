/**
 * [INPUT] useSubscription / useEntitlements hooks (POS: SaaS 配额与订阅状态)
 * [INPUT] useBillingCatalog hook (POS: SaaS catalog + tier_multipliers)
 * [INPUT] QuotaWidgets (POS: QuotaDisplay 子组件与工具函数)
 * [OUTPUT] QuotaDisplay: 账户设置页配额与用量卡片
 * [POS] billing 层配额可视化组件
 */
'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import {
  IconZap,
  IconChat,
  IconSearch,
  IconArrowUp,
  IconActivity,
  IconClock,
  IconWrench,
  IconHardDrive,
  IconGift,
  IconShieldCheck,
  IconChart,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { useQuota, useSubscription } from '@/hooks/billing/useSubscription';
import { useBillingCatalog } from '@/hooks/billing/useBillingCatalog';
import { isSandbox } from '@/lib/deploy-mode';
import { formatNumber, StatCard, PillIndicator, MembershipBadge } from './QuotaWidgets';

interface QuotaDisplayProps {
  className?: string;
  compact?: boolean;
}

export function QuotaDisplay({ className, compact = false }: QuotaDisplayProps) {
  const t = useTranslations('pricing.quota');
  const router = useRouter();
  const sandbox = isSandbox();
  const { quota, isLoading } = useQuota();
  const { subscription, isPro } = useSubscription();
  const { catalog } = useBillingCatalog();

  const stats = useMemo(
    () => ({
      token: { per: quota.tokens.percentage, rem: quota.tokens.remaining },
      chat: {
        per: quota.chats.limit > 0 ? (quota.chats.used / quota.chats.limit) * 100 : 0,
        rem: quota.chats.remaining,
      },
      search: {
        per: quota.searches.limit > 0 ? (quota.searches.used / quota.searches.limit) * 100 : 0,
        rem: quota.searches.remaining,
      },
    }),
    [quota],
  );

  if (isLoading) {
    return <div className="h-10 w-48 bg-black/[0.03] dark:bg-white/5 animate-pulse rounded-full" />;
  }

  // ========== SaaS Sandbox: Work Units with billing transparency ==========
  if (sandbox) {
    if (compact) {
      return (
        <div className={cn('flex flex-col gap-3 p-1', className)}>
          <div className="flex items-center justify-between">
            <MembershipBadge isPro={isPro} size="sm" />
            {!isPro && (
              <button
                onClick={() => router.push('/pricing')}
                className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors uppercase tracking-widest"
              >
                {t('upgrade')}
              </button>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <PillIndicator
              icon={<IconZap className="w-3 h-3 text-amber-500" />}
              value={stats.token.rem}
              percentage={stats.token.per}
              label={t('workUnits')}
            />
          </div>
        </div>
      );
    }

    const subscriptionWu = subscription.subscription_wu ?? 0;
    const topupWu = subscription.topup_wu ?? 0;
    const dailyRefresh = subscription.daily_refresh_remaining_wu ?? 0;
    const freeModels = subscription.free_models ?? [];
    const tierMultipliers = catalog?.tier_multipliers ?? [];

    return (
      <div
        className={cn(
          'relative group overflow-hidden rounded-[2rem] p-1 bg-gradient-to-br from-white/10 via-transparent to-white/5',
          className,
        )}
      >
        <div className="relative z-10 p-6 rounded-[calc(2rem-1px)] bg-background/40 backdrop-blur-3xl">
          <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
            <IconActivity className="w-[100px] h-[100px]" />
          </div>

          {/* Header */}
          <div className="flex items-end justify-between mb-8">
            <div className="space-y-4">
              <MembershipBadge isPro={isPro} />
              <div>
                <h2 className="text-2xl font-black text-foreground tracking-tight">{t('title')}</h2>
                <p className="text-xs font-medium text-muted-foreground/60 uppercase tracking-widest">
                  {t('workUnitsSubtitle')}
                </p>
              </div>
            </div>

            {!isPro && (
              <button
                onClick={() => router.push('/pricing')}
                className={cn(
                  'group/btn flex items-center gap-3 px-6 py-3 rounded-2xl font-bold transition-all overflow-hidden relative',
                  'bg-foreground text-background hover:scale-105 active:scale-95 shadow-2xl shadow-indigo-500/20',
                )}
              >
                <IconArrowUp className="w-4 h-4 transition-transform group-hover/btn:-translate-y-1 group-hover/btn:translate-x-1" />
                {t('upgradeNow')}
              </button>
            )}
          </div>

          {/* WU Balance Card: subscription quota */}
          <div className="mb-6">
            <StatCard
              icon={<IconZap className="w-4.5 h-4.5" />}
              label={t('subscriptionWu')}
              used={Math.max(0, (subscription.monthly_allowance_wu ?? 0) - subscriptionWu)}
              limit={subscription.monthly_allowance_wu ?? 0}
              formatFn={formatNumber}
            />
          </div>

          {/* Topup balance + daily refresh + free models info */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            {topupWu > 0 && (
              <div
                className={cn(
                  'flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl',
                  'bg-black/[0.03] dark:bg-white/5 border border-black/[0.06] dark:border-white/5',
                )}
              >
                <div className="p-1 rounded-full bg-black/[0.03] dark:bg-white/5 text-amber-500/70">
                  <IconGift className="w-3.5 h-3.5" />
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground/50">
                    {t('topupWu')}
                  </span>
                  <span className="text-sm font-black text-foreground/80 tabular-nums">{formatNumber(topupWu)}</span>
                </div>
              </div>
            )}
            {dailyRefresh > 0 && (
              <div
                className={cn(
                  'flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl',
                  'bg-black/[0.03] dark:bg-white/5 border border-black/[0.06] dark:border-white/5',
                )}
              >
                <div className="p-1 rounded-full bg-black/[0.03] dark:bg-white/5 text-emerald-500/70">
                  <IconClock className="w-3.5 h-3.5" />
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground/50">
                    {t('dailyRefresh')}
                  </span>
                  <span className="text-sm font-black text-foreground/80 tabular-nums">
                    {formatNumber(dailyRefresh)}
                  </span>
                </div>
              </div>
            )}
            {freeModels.length > 0 && (
              <div
                className={cn(
                  'flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl col-span-2 sm:col-span-3',
                  'bg-black/[0.03] dark:bg-white/5 border border-black/[0.06] dark:border-white/5',
                )}
              >
                <div className="p-1 rounded-full bg-black/[0.03] dark:bg-white/5 text-indigo-500/70">
                  <IconGift className="w-3.5 h-3.5" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground/50">
                    {t('freeModels')}
                  </span>
                  <span className="text-xs font-medium text-foreground/70 truncate">{freeModels.join(', ')}</span>
                </div>
              </div>
            )}
          </div>

          {/* Tier Multiplier Rate Card */}
          {tierMultipliers.length > 0 && (
            <div className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                <IconChart className="w-3.5 h-3.5 text-muted-foreground/50" />
                <span className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground/50">
                  {t('tierRateCard')}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {tierMultipliers.map((tm) => (
                  <div
                    key={tm.tier}
                    className={cn(
                      'flex flex-col items-center gap-1 px-3 py-2.5 rounded-xl text-center',
                      'bg-black/[0.03] dark:bg-white/5 border border-black/[0.06] dark:border-white/5',
                    )}
                  >
                    <span className="text-lg font-black tabular-nums text-foreground/80">{tm.multiplier}×</span>
                    <span className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground/50">
                      {tm.tier}
                    </span>
                    <span className="text-[9px] text-muted-foreground/40 leading-tight">{tm.examples}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pricing model explainer */}
          <div
            className={cn(
              'mb-6 px-4 py-3 rounded-xl text-[11px] leading-relaxed text-muted-foreground/60',
              'bg-black/[0.02] dark:bg-white/[0.03] border border-black/[0.04] dark:border-white/[0.04]',
            )}
          >
            {t('pricingExplainer')}
          </div>

          {/* Reliability trust bar */}
          <div className="flex items-center gap-2 mb-6 px-4 py-2.5 rounded-xl bg-emerald-500/5 border border-emerald-500/10">
            <IconShieldCheck className="w-4 h-4 text-emerald-500/70 shrink-0" />
            <span className="text-[11px] font-medium text-emerald-600/80 dark:text-emerald-400/80">
              {t('reliabilityTrust')}
            </span>
          </div>

          {/* Footer: reset date + view stats link + billing provider */}
          <div className="flex items-center justify-between pt-6 border-t border-black/[0.06] dark:border-white/5">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground/40 uppercase tracking-widest">
                <IconClock className="w-3 h-3" />
                {t('resetAt')}{' '}
                {new Date(quota.reset_at).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                })}
              </div>
              <button
                onClick={() => router.push('/settings/system')}
                className="flex items-center gap-1 text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors uppercase tracking-widest"
              >
                <IconChart className="w-3 h-3" />
                {t('viewDetailedStats')}
              </button>
            </div>
            <div className="text-[10px] font-medium text-muted-foreground/30">{t('billingMoR')}</div>
          </div>
        </div>
      </div>
    );
  }

  // ========== 紧凑侧边栏模式 ==========
  if (compact) {
    return (
      <div className={cn('flex flex-col gap-3 p-1', className)}>
        <div className="flex items-center justify-between">
          <MembershipBadge isPro={isPro} size="sm" />
          {!isPro && (
            <button
              onClick={() => router.push('/pricing')}
              className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors uppercase tracking-widest"
            >
              {t('upgrade')}
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <PillIndicator
            icon={<IconZap className="w-3 h-3 text-amber-500" />}
            value={stats.token.rem}
            percentage={stats.token.per}
            label={t('tokens')}
          />
          <PillIndicator
            icon={<IconChat className="w-3 h-3 text-blue-500" />}
            value={stats.chat.rem}
            percentage={stats.chat.per}
            label={t('chats')}
          />
          <PillIndicator
            icon={<IconSearch className="w-3 h-3 text-emerald-500" />}
            value={stats.search.rem}
            percentage={stats.search.per}
            label={t('searches')}
          />
        </div>
      </div>
    );
  }

  // ========== 完整设置页模式 ==========
  return (
    <div
      className={cn(
        'relative group overflow-hidden rounded-[2rem] p-1 bg-gradient-to-br from-white/10 via-transparent to-white/5',
        className,
      )}
    >
      <div className="relative z-10 p-6 rounded-[calc(2rem-1px)] bg-background/40 backdrop-blur-3xl">
        {/* 背景装饰图案 */}
        <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
          <IconActivity className="w-[100px] h-[100px]" />
        </div>

        {/* 头部装饰 */}
        <div className="flex items-end justify-between mb-8">
          <div className="space-y-4">
            <MembershipBadge isPro={isPro} />
            <div>
              <h2 className="text-2xl font-black text-foreground tracking-tight">{t('title')}</h2>
              <p className="text-xs font-medium text-muted-foreground/60 uppercase tracking-widest">
                {t('dailyLimitsSubtitle')}
              </p>
            </div>
          </div>

          {!isPro && (
            <button
              onClick={() => router.push('/pricing')}
              className={cn(
                'group/btn flex items-center gap-3 px-6 py-3 rounded-2xl font-bold transition-all overflow-hidden relative',
                'bg-foreground text-background hover:scale-105 active:scale-95 shadow-2xl shadow-indigo-500/20',
              )}
            >
              <IconArrowUp className="w-4 h-4 transition-transform group-hover/btn:-translate-y-1 group-hover/btn:translate-x-1" />
              {t('upgradeToPro')}
            </button>
          )}
        </div>

        {/* 统计网格 */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <StatCard
            icon={<IconZap className="w-4.5 h-4.5" />}
            label={t('tokens')}
            used={quota.tokens.used}
            limit={quota.tokens.limit}
            formatFn={formatNumber}
          />
          <StatCard
            icon={<IconChat className="w-4.5 h-4.5" />}
            label={t('chats')}
            used={quota.chats.used}
            limit={quota.chats.limit}
          />
          <StatCard
            icon={<IconSearch className="w-4.5 h-4.5" />}
            label={t('searches')}
            used={quota.searches.used}
            limit={quota.searches.limit}
          />
        </div>

        {/* 资源限额 */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          {[
            { icon: <IconWrench className="w-3.5 h-3.5" />, label: t('skills'), value: quota.limits.max_skills },
            {
              icon: <IconHardDrive className="w-3.5 h-3.5" />,
              label: t('skillStorage'),
              value: `${quota.limits.max_skill_storage_mb}MB`,
            },
          ].map((item) => (
            <div
              key={item.label}
              className={cn(
                'flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl',
                'bg-black/[0.03] dark:bg-white/5 border border-black/[0.06] dark:border-white/5',
              )}
            >
              <div className="p-1 rounded-full bg-black/[0.03] dark:bg-white/5 text-muted-foreground/60">
                {item.icon}
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground/50">
                  {item.label}
                </span>
                <span className="text-sm font-black text-foreground/80 tabular-nums">{item.value}</span>
              </div>
            </div>
          ))}
        </div>

        {/* 底部信息栏 */}
        <div className="flex items-center justify-between pt-6 border-t border-black/[0.06] dark:border-white/5">
          <div className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground/40 uppercase tracking-widest">
            <IconClock className="w-3 h-3" />
            {t('resetAt')}{' '}
            {new Date(quota.reset_at).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
          <div className="text-[10px] font-medium text-muted-foreground/30">{t('billingMoR')}</div>
        </div>
      </div>
    </div>
  );
}

export default QuotaDisplay;
