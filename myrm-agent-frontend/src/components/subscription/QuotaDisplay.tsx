'use client';

import { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import {
  IconZap,
  IconChat,
  IconSearch,
  IconCrown,
  IconArrowUp,
  IconGlow,
  IconActivity,
  IconClock,
  IconWrench,
  IconHardDrive,
} from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { useQuota, useSubscription } from '@/hooks/useSubscription';
import { isSandbox } from '@/lib/deploy-mode';

/**
 * Premium Quota Display
 *
 * 设计特点：
 * 1. 磨砂玻璃质感 (Backdrop Blur)
 * 2. 渐变发光语义色彩
 * 3. 动态呼吸进度条
 * 4. 紧凑的高级感统计卡片
 */

interface QuotaDisplayProps {
  className?: string;
  compact?: boolean;
}

function formatNumber(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(0)}K`;
  return num.toString();
}

/** 语义化颜色获取 (更高级的 HSL 调频) */
function getUsageStatus(percentage: number) {
  if (percentage >= 90)
    return {
      color: 'text-rose-500',
      bg: 'bg-rose-500',
      glow: 'shadow-[0_0_8px_rgba(244,63,94,0.4)]',
      border: 'border-rose-500/20',
    };
  if (percentage >= 70)
    return {
      color: 'text-amber-500',
      bg: 'bg-amber-500',
      glow: 'shadow-[0_0_8px_rgba(245,158,11,0.4)]',
      border: 'border-amber-500/20',
    };
  return {
    color: 'text-emerald-500',
    bg: 'bg-emerald-500',
    glow: 'shadow-[0_0_8px_rgba(16,185,129,0.4)]',
    border: 'border-emerald-500/20',
  };
}

/** 核心统计卡片组件 */
const StatCard = memo<{
  icon: React.ReactNode;
  label: string;
  used: number;
  limit: number;
  formatFn?: (n: number) => string;
}>(({ icon, label, used, limit, formatFn = String }) => {
  const percentage = (used / limit) * 100;
  const status = getUsageStatus(percentage);
  const remaining = Math.max(0, limit - used);

  return (
    <div
      className={cn(
        'group relative flex-1 min-w-[120px] p-4 rounded-2xl transition-all duration-300',
        'bg-black/[0.03] dark:bg-white/5 backdrop-blur-md border border-black/[0.06] dark:border-white/10',
        'hover:bg-black/[0.06] dark:hover:bg-white/10 hover:scale-[1.02]',
        status.border,
      )}
    >
      {/* 背景光晕装饰 */}
      <div
        className={cn(
          'absolute -top-1 -right-1 w-12 h-12 blur-2xl opacity-0 group-hover:opacity-20 transition-opacity rounded-full',
          status.bg,
        )}
      />

      <div className="flex items-center gap-2 mb-3">
        <div className="p-1.5 rounded-lg bg-black/[0.03] dark:bg-white/5 text-muted-foreground group-hover:text-foreground transition-colors">
          {icon}
        </div>
        <span className="text-[11px] uppercase tracking-wider font-bold text-muted-foreground/70">{label}</span>
      </div>

      <div className="flex items-baseline gap-1.5 mb-3">
        <span className={cn('text-xl font-black tracking-tight', status.color)}>{formatFn(remaining)}</span>
        <span className="text-[10px] font-medium text-muted-foreground/50">/ {formatFn(limit)}</span>
      </div>

      {/* 极简进度条 */}
      <div className="relative h-1 w-full bg-black/[0.04] dark:bg-white/5 rounded-full overflow-hidden">
        <div
          className={cn(
            'absolute top-0 left-0 h-full rounded-full transition-all duration-700 ease-out',
            status.bg,
            status.glow,
          )}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
    </div>
  );
});
StatCard.displayName = 'StatCard';

/** 紧凑型胶囊指示器 */
const PillIndicator = memo<{
  icon: React.ReactNode;
  value: number;
  percentage: number;
  label: string;
}>(({ icon, value, percentage, label }) => {
  const status = getUsageStatus(percentage);

  return (
    <div className="group relative">
      <div
        className={cn(
          'flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] font-bold transition-all',
          'bg-black/[0.03] dark:bg-white/5 border border-black/[0.06] dark:border-white/5 hover:bg-black/[0.06] dark:hover:bg-white/10 hover:border-black/10 dark:hover:border-white/20',
        )}
      >
        <span className="opacity-70 group-hover:opacity-100 transition-opacity">{icon}</span>
        <span className={cn('tabular-nums', status.color)}>{formatNumber(value)}</span>
      </div>

      {/* 悬浮提示框 (手写替代 Tooltip 避免依赖问题) */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-popover text-popover-foreground text-[10px] rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap shadow-xl border border-border z-50">
        {label}: {formatNumber(value)}
      </div>
    </div>
  );
});
PillIndicator.displayName = 'PillIndicator';

/** 套餐勋章 */
const MembershipBadge = memo<{ isPro: boolean; size?: 'sm' | 'md' }>(({ isPro, size = 'md' }) => {
  const t = useTranslations('pricing.quota');
  const isSm = size === 'sm';

  if (isPro) {
    return (
      <div
        className={cn(
          'relative overflow-hidden flex items-center gap-1.5 font-black uppercase tracking-tighter rounded-full',
          isSm ? 'px-2 py-0.5 text-[10px]' : 'px-4 py-1.5 text-xs',
          'bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white shadow-xl shadow-purple-500/20',
        )}
      >
        <IconCrown className={isSm ? 'w-2.5 h-2.5' : 'w-3.5 h-3.5'} />
        {t('proMember')}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent translate-x-[-100%] animate-[shimmer_2s_infinite]" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex items-center gap-1.5 font-black uppercase tracking-tighter rounded-full border border-black/[0.08] dark:border-white/10',
        isSm ? 'px-2 py-0.5 text-[10px]' : 'px-4 py-1.5 text-xs',
        'bg-black/[0.03] dark:bg-white/5 text-muted-foreground',
      )}
    >
      <IconGlow className={isSm ? 'w-2.5 h-2.5' : 'w-3.5 h-3.5'} />
      {t('freeTier')}
    </div>
  );
});
MembershipBadge.displayName = 'MembershipBadge';

export function QuotaDisplay({ className, compact = false }: QuotaDisplayProps) {
  const t = useTranslations('pricing.quota');
  const router = useRouter();
  const sandbox = isSandbox();
  const { quota, isLoading } = useQuota();
  const { isPro } = useSubscription();

  const stats = useMemo(
    () => ({
      token: { per: quota.tokens.percentage, rem: quota.tokens.remaining },
      chat: { per: (quota.chats.used / quota.chats.limit) * 100, rem: quota.chats.remaining },
      search: {
        per: (quota.searches.used / quota.searches.limit) * 100,
        rem: quota.searches.remaining,
      },
    }),
    [quota],
  );

  if (isLoading) {
    return <div className="h-10 w-48 bg-black/[0.03] dark:bg-white/5 animate-pulse rounded-full" />;
  }

  // ========== SaaS Sandbox: Work Units only ==========
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

          <div className="grid grid-cols-1 gap-4 mb-8">
            <StatCard
              icon={<IconZap className="w-4.5 h-4.5" />}
              label={t('workUnits')}
              used={quota.tokens.used}
              limit={quota.tokens.limit}
              formatFn={formatNumber}
            />
          </div>

          <div className="flex items-center justify-between pt-6 border-t border-black/[0.06] dark:border-white/5">
            <div className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground/40 uppercase tracking-widest">
              <IconClock className="w-3 h-3" />
              {t('resetAt')}{' '}
              {new Date(quota.reset_at).toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
              })}
            </div>
            <div className="text-[10px] font-medium text-muted-foreground/30">{t('billingStripe')}</div>
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
          <div className="text-[10px] font-medium text-muted-foreground/30">{t('billingSecure')}</div>
        </div>
      </div>
    </div>
  );
}

export default QuotaDisplay;
