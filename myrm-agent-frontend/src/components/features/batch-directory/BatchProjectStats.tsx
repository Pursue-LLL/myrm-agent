'use client';

/**
 * [INPUT] ./useBatchProjects::BatchProjectsSummary (POS: 聚合统计), next-intl (POS: batchDirectory 文案)
 * [OUTPUT] BatchProjectStats: 项目数 / 运行中 / 已完成任务 / 失败任务四张统计卡
 * [POS] 列表页顶部的聚合统计行；创建向导展开时由页面隐藏。
 */

import { useTranslations } from 'next-intl';
import { Card, CardContent } from '@/components/primitives/card';
import type { BatchProjectsSummary } from './useBatchProjects';

export function BatchProjectStats({ summary }: { summary: BatchProjectsSummary }) {
  const t = useTranslations('batchDirectory');
  const stats = [
    { labelKey: 'statProjects', value: summary.projectCount },
    { labelKey: 'statRunning', value: summary.running },
    { labelKey: 'statCompleted', value: summary.completed },
    { labelKey: 'statFailed', value: summary.failed },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {stats.map(({ labelKey, value }) => (
        <Card key={labelKey}>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">{t(labelKey)}</p>
            <p className="text-2xl font-semibold mt-1">{value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
