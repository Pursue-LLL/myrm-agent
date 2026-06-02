'use client';

import { memo, useState } from 'react';
import { Trash2, X, CheckSquare, FolderInput, FolderX } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { useTranslations } from 'next-intl';
import { useProjectStore } from '@/store/useProjectStore';
import { batchMoveChats } from '@/services/projects';
import useChatStore from '@/store/useChatStore';

interface BatchOperationBarProps {
  selectedCount: number;
  totalCount: number;
  selectedIds: Set<string>;
  isMobile?: boolean;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onDelete: () => void;
  onExit: () => void;
  t: ReturnType<typeof useTranslations>;
}

const BatchOperationBar = memo<BatchOperationBarProps>(
  ({ selectedCount, totalCount, selectedIds, isMobile = false, onSelectAll, onDeselectAll, onDelete, onExit, t }) => {
    const projects = useProjectStore((s) => s.projects);
    const [showProjectPicker, setShowProjectPicker] = useState(false);

    const handleBatchMove = async (projectId: string | null) => {
      const ids = [...selectedIds];
      await batchMoveChats(ids, projectId);
      const items = useChatStore.getState().chatHistoryItems;
      useChatStore.setState({
        chatHistoryItems: items.map((item) => (selectedIds.has(item.id) ? { ...item, projectId } : item)),
      });
      setShowProjectPicker(false);
    };

    return (
      <div className="space-y-1">
        <div
          className={cn(
            'flex items-center gap-2 px-2 py-1.5 rounded-lg',
            'bg-primary/5 dark:bg-primary/10 border border-primary/15',
          )}
        >
          <button
            onClick={onExit}
            className="p-1 rounded hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            title={t('chat.batch.exit')}
          >
            <X size={14} className="text-muted-foreground" />
          </button>

          <span className={cn('text-xs font-medium text-primary flex-1', isMobile && 'text-[11px]')}>
            {t('chat.batch.selected', { count: selectedCount })}
          </span>

          <button
            onClick={selectedCount === totalCount ? onDeselectAll : onSelectAll}
            className={cn(
              'flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors',
              'hover:bg-black/5 dark:hover:bg-white/5 text-muted-foreground',
              isMobile && 'text-[11px]',
            )}
          >
            <CheckSquare size={12} />
            {selectedCount === totalCount ? t('chat.batch.deselectAll') : t('chat.batch.selectAll')}
          </button>

          {projects.length > 0 && (
            <button
              onClick={() => setShowProjectPicker(!showProjectPicker)}
              disabled={selectedCount === 0}
              className={cn(
                'flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors',
                selectedCount > 0 ? 'text-primary hover:bg-primary/10' : 'text-muted-foreground/40 cursor-not-allowed',
                isMobile && 'text-[11px]',
              )}
            >
              <FolderInput size={12} />
              {t('project.moveTo')}
            </button>
          )}

          <button
            onClick={onDelete}
            disabled={selectedCount === 0}
            className={cn(
              'flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors',
              selectedCount > 0
                ? 'text-destructive hover:bg-destructive/10'
                : 'text-muted-foreground/40 cursor-not-allowed',
              isMobile && 'text-[11px]',
            )}
          >
            <Trash2 size={12} />
            {t('chat.batch.delete')}
          </button>
        </div>

        {showProjectPicker && selectedCount > 0 && (
          <div className="flex items-center gap-1 flex-wrap px-2 py-1 rounded-lg bg-black/3 dark:bg-white/3">
            <button
              onClick={() => handleBatchMove(null)}
              className="flex items-center gap-1 h-5 px-2 rounded-full text-[10px] font-medium bg-black/5 dark:bg-white/8 hover:bg-black/10 dark:hover:bg-white/12 text-muted-foreground transition-colors"
            >
              <FolderX size={10} />
              {t('project.removeFromProject')}
            </button>
            {projects.map((p) => (
              <button
                key={p.id}
                onClick={() => handleBatchMove(p.id)}
                className="flex items-center gap-1 h-5 px-2 rounded-full text-[10px] font-medium bg-black/5 dark:bg-white/8 hover:bg-black/10 dark:hover:bg-white/12 text-foreground/80 transition-colors"
              >
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: p.color }} />
                {p.name}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  },
);

BatchOperationBar.displayName = 'BatchOperationBar';

export default BatchOperationBar;
