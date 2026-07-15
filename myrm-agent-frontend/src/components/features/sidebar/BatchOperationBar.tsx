'use client';

import { memo, useCallback, useRef, useState } from 'react';
import { Trash2, X, CheckSquare, FolderInput, FolderX, Loader2, Download } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { useTranslations } from 'next-intl';
import { useProjectStore } from '@/store/useProjectStore';
import { batchMoveChats } from '@/services/projects';
import useChatStore from '@/store/useChatStore';
import { toast } from '@/hooks/useToast';
import {
  batchExportAsZip,
  downloadBlob,
  type BatchExportFormat,
  type BatchExportProgress,
} from '@/lib/utils/batchExport';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';

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

const EXPORT_FORMATS: { key: BatchExportFormat; labelKey: string }[] = [
  { key: 'markdown', labelKey: 'chat.batch.exportFormatMarkdown' },
  { key: 'json', labelKey: 'chat.batch.exportFormatJson' },
  { key: 'html', labelKey: 'chat.batch.exportFormatHtml' },
];

const BatchOperationBar = memo<BatchOperationBarProps>(
  ({ selectedCount, totalCount, selectedIds, isMobile = false, onSelectAll, onDeselectAll, onDelete, onExit, t }) => {
    const projects = useProjectStore((s) => s.projects);
    const [showProjectPicker, setShowProjectPicker] = useState(false);
    const [moving, setMoving] = useState(false);

    const [exporting, setExporting] = useState(false);
    const [exportProgress, setExportProgress] = useState<BatchExportProgress | null>(null);
    const [formatPickerOpen, setFormatPickerOpen] = useState(false);
    const abortRef = useRef<AbortController | null>(null);

    const handleBatchMove = async (projectId: string | null) => {
      if (moving) return;
      setMoving(true);
      try {
        const ids = [...selectedIds];
        await batchMoveChats(ids, projectId);
        const items = useChatStore.getState().chatHistoryItems;
        useChatStore.setState({
          chatHistoryItems: items.map((item) => (selectedIds.has(item.id) ? { ...item, projectId } : item)),
        });
        toast(t('project.moveSuccess', { count: ids.length }));
      } catch (error) {
        toast({
          title: t('project.moveFailed'),
          description: error instanceof Error ? error.message : undefined,
          variant: 'destructive',
        });
      } finally {
        setMoving(false);
        setShowProjectPicker(false);
      }
    };

    const handleExport = useCallback(
      async (format: BatchExportFormat) => {
        if (exporting || selectedCount === 0) return;
        setFormatPickerOpen(false);
        setExporting(true);
        setExportProgress(null);

        const controller = new AbortController();
        abortRef.current = controller;

        const isDark = document.documentElement.classList.contains('dark');
        const lang = navigator.language.startsWith('zh') ? 'zh' : 'en';

        try {
          const { blob, result } = await batchExportAsZip([...selectedIds], format, {
            theme: isDark ? 'dark' : 'light',
            lang: lang as 'en' | 'zh',
            onProgress: setExportProgress,
            signal: controller.signal,
          });

          if (result.exported === 0) {
            toast({ title: t('chat.exportChat.noMessages'), variant: 'default' });
            return;
          }

          const date = new Date().toISOString().slice(0, 10);
          downloadBlob(blob, `myrm-export-${date}.zip`);

          let msg = t('chat.batch.exportComplete', { exported: result.exported });
          if (result.skipped > 0 || result.failed > 0) {
            msg += ` (${t('chat.batch.exportPartial', { skipped: result.skipped, failed: result.failed })})`;
          }
          toast(msg);
        } catch (err) {
          if (err instanceof DOMException && err.name === 'AbortError') return;
          console.error('[BatchExport]', err);
          toast({ title: t('chat.batch.exportFailed'), variant: 'destructive' });
        } finally {
          setExporting(false);
          setExportProgress(null);
          abortRef.current = null;
        }
      },
      [exporting, selectedCount, selectedIds, t],
    );

    const handleCancelExport = useCallback(() => {
      abortRef.current?.abort();
    }, []);

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

          <Popover open={formatPickerOpen} onOpenChange={setFormatPickerOpen}>
            <PopoverTrigger asChild>
              <button
                disabled={selectedCount === 0 || exporting}
                className={cn(
                  'flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors',
                  selectedCount > 0 && !exporting
                    ? 'text-primary hover:bg-primary/10'
                    : 'text-muted-foreground/40 cursor-not-allowed',
                  isMobile && 'text-[11px]',
                )}
              >
                {exporting ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                {t('chat.batch.export')}
              </button>
            </PopoverTrigger>
            <PopoverContent side="bottom" align="end" className="w-36 p-1">
              {EXPORT_FORMATS.map(({ key, labelKey }) => (
                <button
                  key={key}
                  onClick={() => handleExport(key)}
                  className="w-full text-left px-3 py-1.5 text-xs rounded hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                >
                  {t(labelKey)}
                </button>
              ))}
            </PopoverContent>
          </Popover>

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

        {exporting && exportProgress && (
          <div className="flex items-center gap-2 px-2 py-1 rounded-lg bg-primary/5 dark:bg-primary/10">
            <Loader2 size={10} className="animate-spin text-primary flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-0.5">
                <span className="truncate">{exportProgress.currentTitle}</span>
                <span>
                  {t('chat.batch.exportProgress', {
                    current: exportProgress.current,
                    total: exportProgress.total,
                  })}
                </span>
              </div>
              <div className="h-1 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-200"
                  style={{ width: `${(exportProgress.current / exportProgress.total) * 100}%` }}
                />
              </div>
            </div>
            <button
              onClick={handleCancelExport}
              className="text-[10px] text-muted-foreground hover:text-destructive transition-colors flex-shrink-0"
            >
              {t('chat.batch.exportCancel')}
            </button>
          </div>
        )}

        {showProjectPicker && selectedCount > 0 && (
          <div className="flex items-center gap-1 flex-wrap px-2 py-1 rounded-lg bg-black/3 dark:bg-white/3">
            {moving && <Loader2 size={10} className="animate-spin text-primary" />}
            <button
              onClick={() => handleBatchMove(null)}
              disabled={moving}
              className="flex items-center gap-1 h-5 px-2 rounded-full text-[10px] font-medium bg-black/5 dark:bg-white/8 hover:bg-black/10 dark:hover:bg-white/12 text-muted-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <FolderX size={10} />
              {t('project.removeFromProject')}
            </button>
            {projects.map((p) => (
              <button
                key={p.id}
                onClick={() => handleBatchMove(p.id)}
                disabled={moving}
                className="flex items-center gap-1 h-5 px-2 rounded-full text-[10px] font-medium bg-black/5 dark:bg-white/8 hover:bg-black/10 dark:hover:bg-white/12 text-foreground/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
