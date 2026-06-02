'use client';

import React, { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { History, ChevronDown, ChevronUp, RotateCcw, Check, Clock, AlertTriangle } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { ArtifactVersion } from '@/store/chat/types';

interface VersionHistoryProps {
  /** 版本列表 */
  versions: ArtifactVersion[];
  /** 当前查看的版本索引（-1 表示最新） */
  viewingIndex: number;
  /** 是否正在生成中 */
  isGenerating: boolean;
  /** 切换版本回调 */
  onSwitchVersion: (index: number) => void;
  /** 回滚版本回调 */
  onRollback: (index: number) => void;
}

/** 格式化相对时间 */
function formatRelativeTime(dateString: string, t: ReturnType<typeof useTranslations>): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return t('versions.justNow');
  if (diffMins < 60) return t('versions.minutesAgo', { count: diffMins });
  if (diffHours < 24) return t('versions.hoursAgo', { count: diffHours });
  if (diffDays < 7) return t('versions.daysAgo', { count: diffDays });

  return date.toLocaleDateString();
}

const VersionHistory: React.FC<VersionHistoryProps> = ({
  versions,
  viewingIndex,
  isGenerating,
  onSwitchVersion,
  onRollback,
}) => {
  const t = useTranslations('artifacts');
  const [isOpen, setIsOpen] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);

  const hasVersions = versions.length > 0;
  const isViewingHistory = viewingIndex >= 0;
  const currentVersionNumber = isViewingHistory
    ? versions[viewingIndex]?.versionNumber
    : versions.length > 0
      ? versions[versions.length - 1].versionNumber
      : 0;

  const handleSwitchVersion = useCallback(
    (index: number) => {
      onSwitchVersion(index);
      setIsOpen(false);
    },
    [onSwitchVersion],
  );

  const handleRollbackClick = useCallback((index: number, e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setRollbackTarget(index);
    setIsOpen(false);
  }, []);

  const confirmRollback = useCallback(() => {
    if (rollbackTarget !== null) {
      onRollback(rollbackTarget);
      setRollbackTarget(null);
    }
  }, [rollbackTarget, onRollback]);

  if (!hasVersions) {
    return null;
  }

  return (
    <>
      <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button
                variant={isViewingHistory ? 'secondary' : 'ghost'}
                size="sm"
                className={cn(
                  'gap-1.5 px-2 h-8',
                  isViewingHistory && 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
                )}
                disabled={isGenerating}
                aria-label={t('versions.history')}
              >
                <History className="h-4 w-4" />
                <span className="text-xs font-medium">v{currentVersionNumber}</span>
                {isOpen ? <ChevronUp className="h-3 w-3 ml-0.5" /> : <ChevronDown className="h-3 w-3 ml-0.5" />}
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p>{t('versions.history')}</p>
            <p className="text-xs text-muted-foreground">{t('versions.totalVersions', { count: versions.length })}</p>
          </TooltipContent>
        </Tooltip>

        <DropdownMenuContent align="end" className="w-72 max-h-80 overflow-auto" sideOffset={8}>
          {/* 最新版本选项 */}
          <DropdownMenuItem
            className={cn(
              'flex items-center justify-between py-2.5 cursor-pointer',
              !isViewingHistory && 'bg-primary/10',
            )}
            onClick={() => handleSwitchVersion(-1)}
          >
            <div className="flex items-center gap-2">
              <Badge variant="default" className="text-xs px-1.5">
                {t('versions.latest')}
              </Badge>
              <span className="text-sm">{t('versions.currentVersion')}</span>
            </div>
            {!isViewingHistory && <Check className="h-4 w-4 text-primary" />}
          </DropdownMenuItem>

          {versions.length > 0 && <DropdownMenuSeparator />}

          {/* 历史版本列表（倒序显示） */}
          {[...versions].reverse().map((version, reverseIndex) => {
            const actualIndex = versions.length - 1 - reverseIndex;
            const isSelected = viewingIndex === actualIndex;
            const isLatest = actualIndex === versions.length - 1;

            return (
              <DropdownMenuItem
                key={version.versionId}
                className={cn('flex flex-col items-start py-2.5 cursor-pointer group', isSelected && 'bg-primary/10')}
                onClick={() => handleSwitchVersion(actualIndex)}
              >
                <div className="flex items-center justify-between w-full">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">v{version.versionNumber}</span>
                    {isLatest && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0">
                        {t('versions.latest')}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {isSelected && <Check className="h-4 w-4 text-primary" />}
                    {!isLatest && !isSelected && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={(e) => handleRollbackClick(actualIndex, e)}
                        aria-label={t('versions.rollback')}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  <span>{formatRelativeTime(version.createdAt, t)}</span>
                </div>

                {version.description && (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{version.description}</p>
                )}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* 回滚确认对话框 */}
      <AlertDialog open={rollbackTarget !== null} onOpenChange={(open: boolean) => !open && setRollbackTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              {t('versions.rollbackConfirm.title')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('versions.rollbackConfirm.description', {
                version: rollbackTarget !== null ? versions[rollbackTarget]?.versionNumber : 0,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('versions.rollbackConfirm.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmRollback} className="bg-amber-600 hover:bg-amber-700">
              {t('versions.rollbackConfirm.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

/** 历史版本查看提示条（单独导出，在 ArtifactPortal 中使用） */
export const VersionHistoryBanner: React.FC<{
  versions: ArtifactVersion[];
  viewingIndex: number;
  onBackToLatest: () => void;
}> = ({ versions, viewingIndex, onBackToLatest }) => {
  const t = useTranslations('artifacts');
  const isViewingHistory = viewingIndex >= 0;

  if (!isViewingHistory || !versions[viewingIndex]) {
    return null;
  }

  return (
    <div className="bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-200 text-xs py-1.5 px-3 flex items-center justify-between border-b border-amber-200 dark:border-amber-800">
      <span className="flex items-center gap-1.5">
        <History className="h-3.5 w-3.5" />
        {t('versions.viewingHistoryBanner', {
          version: versions[viewingIndex].versionNumber,
        })}
      </span>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 text-xs hover:bg-amber-200 dark:hover:bg-amber-800"
        onClick={onBackToLatest}
      >
        {t('versions.backToLatest')}
      </Button>
    </div>
  );
};

export default VersionHistory;
