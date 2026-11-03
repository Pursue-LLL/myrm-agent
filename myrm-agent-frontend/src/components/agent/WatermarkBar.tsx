/**
 * [INPUT]
 * - @/services/memory/profileNotes: LayerWatermarkResponse, WatermarkLevel
 * - @/components/primitives: Badge
 * - next-intl::useTranslations (POS: Internationalization hook)
 *
 * [OUTPUT]
 * - WatermarkBar: capacity gauge of one memory layer (used / limit characters, level badge, server warning)
 * - levelForRatio: the watermark level a usage ratio falls into
 *
 * [POS]
 * Shared by the dual-layer memory card: the gauge shows what the server reported after a load or a save, and
 * `levelForRatio` re-derives the level locally while the user is still typing, so both agree on the thresholds.
 */

'use client';

import { AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type { LayerWatermarkResponse, WatermarkLevel } from '@/services/memory/profileNotes';

interface LevelStyle {
  variant: 'default' | 'secondary' | 'destructive';
  badgeClassName: string;
  barClassName: string;
}

const LEVEL_STYLES: Record<WatermarkLevel, LevelStyle> = {
  safe: { variant: 'default', badgeClassName: 'bg-emerald-600 text-white', barClassName: 'bg-emerald-500' },
  warning: { variant: 'secondary', badgeClassName: 'bg-amber-500 text-white', barClassName: 'bg-amber-500' },
  critical: { variant: 'secondary', badgeClassName: 'bg-orange-600 text-white', barClassName: 'bg-orange-500' },
  overflow: { variant: 'destructive', badgeClassName: 'bg-rose-600 text-white', barClassName: 'bg-rose-600' },
};

const WARNING_RATIO = 0.7;
const CRITICAL_RATIO = 0.9;

export function levelForRatio(ratio: number): WatermarkLevel {
  if (ratio > 1) {
    return 'overflow';
  }
  if (ratio >= CRITICAL_RATIO) {
    return 'critical';
  }
  return ratio >= WARNING_RATIO ? 'warning' : 'safe';
}

export function WatermarkBar({ watermark }: { watermark: LayerWatermarkResponse }) {
  const t = useTranslations('memory.dualLayer');
  const percent = Math.min(Math.round(watermark.usage_ratio * 100), 100);
  const style = LEVEL_STYLES[watermark.level];

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs font-medium">
        <span className="text-muted-foreground">
          {t('capacity', { current: watermark.current_chars, max: watermark.max_chars, percent })}
        </span>
        <Badge variant={style.variant} className={cn('text-[10px] px-1.5 py-0', style.badgeClassName)}>
          {t(`level.${watermark.level}`)}
        </Badge>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn('h-full transition-all duration-300', style.barClassName)}
          style={{ width: `${percent}%` }}
        />
      </div>
      {watermark.warning_message && (
        <p className="flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span>{watermark.warning_message}</span>
        </p>
      )}
    </div>
  );
}
