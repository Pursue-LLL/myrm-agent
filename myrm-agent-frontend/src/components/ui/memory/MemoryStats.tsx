'use client';

import { memo, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { useMemoryStore, type MemoryType } from '@/store/memory';
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

  useEffect(() => {
    if (!memoryStats) fetchMemoryStats();
  }, [memoryStats, fetchMemoryStats]);

  if (statsLoading && !memoryStats) return null;
  if (!memoryStats) return null;

  return (
    <div className={cn('grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2', className)}>
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
  );
});

MemoryStats.displayName = 'MemoryStats';

export default MemoryStats;
