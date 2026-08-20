/**
 * [INPUT] skeleton::Skeleton (POS: 基础微光脉冲占位基元), classnameUtils::cn (POS: Tailwind 类名合并工具)
 * [OUTPUT] ListSkeleton, CardGridSkeleton, TableSkeleton, FormSkeleton, ListDetailSkeleton: 常用结构骨架模板
 * [POS] UI基元层。提供多种标准化页面拓扑骨架模板，消除加载阶段布局跳动(CLS)。
 */

import * as React from 'react';
import { Skeleton } from './skeleton';
import { cn } from '@/lib/utils/classnameUtils';

/**
 * 列表拓扑骨架模板（支持多行列表项）
 */
export function ListSkeleton({
  count = 3,
  className,
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading list"
      className={cn('space-y-3', className)}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3.5 rounded-xl border border-border/40 bg-card/40 p-3.5 shadow-sm"
        >
          <Skeleton className="h-10 w-10 shrink-0 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-2/3" />
          </div>
          <Skeleton className="h-8 w-16 shrink-0 rounded-full" />
        </div>
      ))}
    </div>
  );
}

/**
 * 卡片网格拓扑骨架模板
 */
export function CardGridSkeleton({
  count = 4,
  columns = 2,
  className,
}: {
  count?: number;
  columns?: 1 | 2 | 3 | 4;
  className?: string;
}) {
  const gridColsClass =
    columns === 1
      ? 'grid-cols-1'
      : columns === 2
        ? 'grid-cols-1 sm:grid-cols-2'
        : columns === 3
          ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
          : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4';

  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading cards"
      className={cn('grid gap-3.5', gridColsClass, className)}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex flex-col justify-between rounded-xl border border-border/40 bg-card/40 p-4 space-y-3 shadow-sm"
        >
          <div className="space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <Skeleton className="h-5 w-28" />
              <Skeleton className="h-4 w-12 rounded-full" />
            </div>
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-4/5" />
          </div>
          <div className="pt-2 flex items-center justify-between border-t border-border/30">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-16 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * 表格拓扑骨架模板
 */
export function TableSkeleton({
  rows = 5,
  columns = 4,
  className,
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading table"
      className={cn(
        'overflow-hidden rounded-xl border border-border/50 bg-card/40 shadow-sm',
        className,
      )}
    >
      <div className="flex items-center border-b border-border/50 bg-muted/40 p-3.5 gap-4">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton key={i} className="h-4 flex-1" />
        ))}
      </div>
      <div className="divide-y divide-border/30">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex items-center p-3.5 gap-4">
            {Array.from({ length: columns }).map((_, c) => (
              <Skeleton
                key={c}
                className={cn('h-3.5 flex-1', c === 0 ? 'w-1/4' : 'w-full')}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * 设置/表单拓扑骨架模板
 */
export function FormSkeleton({
  count = 3,
  className,
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading form"
      className={cn('space-y-6', className)}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-10 w-full rounded-xl" />
          <Skeleton className="h-3 w-48" />
        </div>
      ))}
    </div>
  );
}

/**
 * 左右双栏结构骨架模板（用于工件库、主从详情等）
 */
export function ListDetailSkeleton({
  className,
}: {
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading workspace"
      className={cn(
        'flex h-full w-full rounded-xl border border-border/50 bg-background overflow-hidden',
        className,
      )}
    >
      <div className="w-1/3 border-r border-border/40 bg-muted/10 p-4 space-y-3">
        <div className="flex items-center gap-2 mb-4">
          <Skeleton className="h-5 w-5 rounded" />
          <Skeleton className="h-5 w-28" />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-border/30 p-3 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        ))}
      </div>
      <div className="flex-1 p-6 space-y-4">
        <div className="space-y-2 border-b border-border/30 pb-4">
          <Skeleton className="h-7 w-1/3" />
          <Skeleton className="h-4 w-1/2" />
        </div>
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    </div>
  );
}
