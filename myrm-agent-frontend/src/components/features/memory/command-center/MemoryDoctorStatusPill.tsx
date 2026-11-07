'use client';

/**
 * [INPUT] ./memoryDoctorModel (POS: 就绪度取值守卫与翻译函数类型)
 * [OUTPUT] StatusPill: 就绪度状态徽章（ready / warning / missing / critical 按语义着色）
 * [POS] Doctor 面板的状态徽章，趋势区、运行摘要与检查项共用同一套着色。
 */

import { type MemoryTranslation, isReadinessStatus } from './memoryDoctorModel';

export const StatusPill = ({ status, t }: { status: string; t: MemoryTranslation }) => (
  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${statusClassName(status)}`}>
    {isReadinessStatus(status) ? t(`commandCenter.readinessStatus.${status}`) : status}
  </span>
);

const statusClassName = (status: string): string => {
  if (status === 'ready') {
    return 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
  }
  if (status === 'warning' || status === 'missing') {
    return 'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300';
  }
  if (status === 'critical') {
    return 'border-destructive/20 bg-destructive/10 text-destructive-text';
  }
  return 'border-border bg-background text-muted-foreground';
};
