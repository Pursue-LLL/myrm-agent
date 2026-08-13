'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Tag } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useMemoryStore, type MemoryType } from '@/store/memory';
import { getMemoryTags, type TagStatsItem } from '@/services/memory';
import MemoryTypeIcon from './MemoryTypeIcon';

const MEMORY_TYPES: MemoryType[] = [
  'profile',
  'semantic',
  'episodic',
  'procedural',
  'conversation',
  'claim',
  'task_digest',
];

const MemoryStats = memo<{ className?: string }>(({ className }) => {
  const t = useTranslations('memory');
  const { memoryStats, statsLoading, fetchMemoryStats } = useMemoryStore();
  const [topTags, setTopTags] = useState<TagStatsItem[]>([]);

  useEffect(() => {
    if (!memoryStats) fetchMemoryStats();
  }, [memoryStats, fetchMemoryStats]);

  useEffect(() => {
    getMemoryTags(5).then((res) => setTopTags(res.tags)).catch(() => {});
  }, [memoryStats]);

  if (statsLoading && !memoryStats) return null;
  if (!memoryStats) return null;

  return (
    <div className={cn('space-y-2', className)}>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        <div
          className={cn(
            'flex flex-col items-center justify-center p-3 rounded-xl',
            'bg-primary/5 border border-primary/10',
            'col-span-2 sm:col-span-1',
          )}
        >
          <span className="text-2xl font-bold text-primary">{memoryStats.total_memories}</span>
          <span className="text-[10px] text-muted-foreground mt-1">{t('stats.total')}</span>
        </div>

        {MEMORY_TYPES.map((type) => (
          <div
            key={type}
            className={cn(
              'flex flex-col items-center justify-center p-3 rounded-xl',
              'bg-accent/30 border border-border/50',
            )}
          >
            <MemoryTypeIcon type={type} size={14} />
            <span className="text-lg font-semibold text-foreground mt-1">{memoryStats.by_type[type] ?? 0}</span>
            <span className="text-[10px] text-muted-foreground mt-0.5 text-center">{t(`types.${type}`)}</span>
          </div>
        ))}
      </div>

      {topTags.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap px-1">
          <Tag size={12} className="text-muted-foreground/50 shrink-0" />
          <span className="text-[11px] text-muted-foreground/60 mr-0.5">{t('stats.topTags')}:</span>
          {topTags.map(({ tag, count }) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent/60 text-[11px] text-muted-foreground"
            >
              {tag}
              <span className="opacity-50">{count}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
});

MemoryStats.displayName = 'MemoryStats';

export default MemoryStats;
