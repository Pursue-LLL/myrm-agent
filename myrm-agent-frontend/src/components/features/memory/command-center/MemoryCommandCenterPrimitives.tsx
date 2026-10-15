'use client';

/**
 * [INPUT]
 * @/lib/utils/classnameUtils::cn (POS: Tailwind 类名合并工具)
 *
 * [OUTPUT]
 * Panel: 带标题与实时提示的版块容器。
 * MetricTile / RuntimeRow: 指标块与运行时状态行（支持告警态）。
 * EmptyState: 虚线空态占位。
 *
 * [POS]
 * 个人大脑指挥中心的版块、指标块、运行时行与空态原子组件，供各分区面板共用。
 */

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils/classnameUtils';

export const Panel = ({
  title,
  liveHint,
  className,
  children,
}: {
  title: string;
  liveHint?: string;
  className?: string;
  children: ReactNode;
}) => (
  <div className={cn('space-y-3', className)}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      {liveHint ? (
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-primary/80">
          <span
            aria-hidden
            className="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_8px] shadow-primary/55 animate-pulse"
          />
          {liveHint}
        </span>
      ) : null}
    </div>
    {children}
  </div>
);

export const MetricTile = ({
  label,
  value,
  dense = false,
}: {
  label: string;
  value: number | string;
  dense?: boolean;
}) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="text-xs font-medium text-muted-foreground">{label}</div>
    <div className={cn('mt-1 font-semibold text-foreground', dense ? 'text-lg' : 'text-2xl')}>{value}</div>
  </div>
);

export const RuntimeRow = ({ label, value, alert }: { label: string; value: string; alert?: boolean }) => (
  <div
    className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 ${
      alert ? 'border-amber-500/50 bg-amber-500/10' : 'border-border/50 bg-accent/20'
    }`}
  >
    <span className="text-xs text-muted-foreground">{label}</span>
    <span
      className={`truncate text-right text-xs font-medium ${
        alert ? 'text-amber-700 dark:text-amber-300' : 'text-foreground'
      }`}
    >
      {value}
    </span>
  </div>
);

export const EmptyState = ({ label }: { label: string }) => (
  <div className="rounded-lg border border-dashed border-border/70 p-4 text-sm text-muted-foreground">{label}</div>
);
