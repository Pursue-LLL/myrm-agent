'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { IconGlobe, IconWifi } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import type { ChannelIngressMode } from '@/lib/channels/connectivity';

interface ChannelIngressBadgeProps {
  mode: ChannelIngressMode;
  className?: string;
}

export function ChannelIngressBadge({ mode, className }: ChannelIngressBadgeProps) {
  const t = useTranslations('channels');
  const isOutbound = mode === 'outbound';

  return (
    <div className={cn('min-w-0 max-w-full space-y-1', className)}>
      <span
        className={cn(
          'inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
          isOutbound
            ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
            : 'border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400',
        )}
      >
        {isOutbound ? <IconWifi className="h-3.5 w-3.5 shrink-0" /> : <IconGlobe className="h-3.5 w-3.5 shrink-0" />}
        <span className="truncate">{isOutbound ? t('connectivityBadgeOutbound') : t('connectivityBadgeInbound')}</span>
      </span>
      {!isOutbound && (
        <p className="text-xs text-muted-foreground leading-relaxed break-words">
          {t('connectivityBadgeInboundHint')}{' '}
          <Link
            href="/settings/system#public-ingress"
            className="text-primary underline underline-offset-2 hover:text-primary/80"
          >
            {t('connectivityBadgeIngressLink')}
          </Link>
        </p>
      )}
    </div>
  );
}
