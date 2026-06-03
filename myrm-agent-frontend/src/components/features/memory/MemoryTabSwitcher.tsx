'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';

export type MemoryTab = 'pending' | 'all' | 'context' | 'shared' | 'recall' | 'trash';

interface MemoryTabSwitcherProps {
  activeTab: MemoryTab;
  pendingCount: number;
  totalCount?: number;
  archivedCount?: number;
  onChange: (tab: MemoryTab) => void;
}

const MemoryTabSwitcher = memo<MemoryTabSwitcherProps>(
  ({ activeTab, pendingCount, totalCount, archivedCount, onChange }) => {
    const t = useTranslations('memory');

    return (
      <div className="grid grid-cols-2 gap-1 rounded-xl bg-accent/50 p-1 sm:grid-cols-6">
        <button
          onClick={() => onChange('pending')}
          className={cn(
            'flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
            'text-sm font-medium transition-all duration-200',
            activeTab === 'pending' ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t('pending')}
          {pendingCount > 0 && (
            <span
              className={cn(
                'flex h-5 min-w-[20px] items-center justify-center',
                'rounded-full px-1.5 text-xs font-bold',
                activeTab === 'pending' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
              )}
            >
              {pendingCount > 99 ? '99+' : pendingCount}
            </span>
          )}
        </button>
        <button
          onClick={() => onChange('all')}
          className={cn(
            'flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
            'text-sm font-medium transition-all duration-200',
            activeTab === 'all' ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t('filterAll')}
          {totalCount !== undefined && <span className="text-xs text-muted-foreground">({totalCount})</span>}
        </button>
        <button
          onClick={() => onChange('context')}
          className={cn(
            'flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
            'text-sm font-medium transition-all duration-200',
            activeTab === 'context' ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t('context.tab')}
        </button>
        <button
          onClick={() => onChange('shared')}
          className={cn(
            'flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
            'text-sm font-medium transition-all duration-200',
            activeTab === 'shared' ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t('sharedContexts.tab')}
        </button>
        <button
          onClick={() => onChange('recall')}
          className={cn(
            'flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
            'text-sm font-medium transition-all duration-200',
            activeTab === 'recall' ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t('conversationRecall.tab')}
        </button>
        <button
          onClick={() => onChange('trash')}
          className={cn(
            'flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
            'text-sm font-medium transition-all duration-200',
            activeTab === 'trash' ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t('trash.tab')}
          {archivedCount !== undefined && archivedCount > 0 && (
            <span className="text-xs text-muted-foreground">({archivedCount})</span>
          )}
        </button>
      </div>
    );
  },
);

MemoryTabSwitcher.displayName = 'MemoryTabSwitcher';

export default MemoryTabSwitcher;
