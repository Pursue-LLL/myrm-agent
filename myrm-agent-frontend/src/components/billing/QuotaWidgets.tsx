/**
 * [INPUT] PremiumIcons (POS: SVG 图标库)
 * [OUTPUT] formatNumber, getUsageStatus, StatCard, PillIndicator, MembershipBadge
 * [POS] QuotaDisplay 子组件与工具函数
 */
import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconCrown, IconGlow } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

export function formatNumber(num: number): string {
  if (num >= 1000000) {return `${(num / 1000000).toFixed(1)}M`;}
  if (num >= 1000) {return `${(num / 1000).toFixed(0)}K`;}
  return num.toString();
}

export function getUsageStatus(percentage: number) {
  if (percentage >= 90)
    {return {
      color: 'text-rose-500',
      bg: 'bg-rose-500',
      glow: 'shadow-[0_0_8px_rgba(244,63,94,0.4)]',
      border: 'border-rose-500/20',
    };}
  if (percentage >= 70)
    {return {
      color: 'text-amber-500',
      bg: 'bg-amber-500',
      glow: 'shadow-[0_0_8px_rgba(245,158,11,0.4)]',
      border: 'border-amber-500/20',
    };}
  return {
    color: 'text-emerald-500',
    bg: 'bg-emerald-500',
    glow: 'shadow-[0_0_8px_rgba(16,185,129,0.4)]',
    border: 'border-emerald-500/20',
  };
}

export const StatCard = memo<{
  icon: React.ReactNode;
  label: string;
  used: number;
  limit: number;
  formatFn?: (n: number) => string;
}>(({ icon, label, used, limit, formatFn = String }) => {
  const percentage = limit > 0 ? (used / limit) * 100 : 0;
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

export const PillIndicator = memo<{
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

      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-popover text-popover-foreground text-[10px] rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap shadow-xl border border-border z-50">
        {label}: {formatNumber(value)}
      </div>
    </div>
  );
});
PillIndicator.displayName = 'PillIndicator';

export const MembershipBadge = memo<{ isPro: boolean; size?: 'sm' | 'md' }>(({ isPro, size = 'md' }) => {
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
