'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Layers,
  ChevronDown,
  ChevronUp,
  UserCheck,
  Bot,
  X,
  ExternalLink,
  RefreshCw,
  Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  fetchTaskSpaces,
  closeTaskSpace,
  toggleTaskSpaceTakeover,
  fetchTaskSpaceSnapshot,
  type TaskSpaceInfo,
  type TaskSpaceSnapshot,
} from '@/services/browserTaskSpaces';

export interface TaskSpaceDockProps {
  className?: string;
  autoRefreshIntervalMs?: number;
}

export const TaskSpaceDock: React.FC<TaskSpaceDockProps> = ({
  className,
  autoRefreshIntervalMs = 5000,
}) => {
  const t = useTranslations('taskSpaces');
  const [spaces, setSpaces] = useState<TaskSpaceInfo[]>([]);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [activeSnapshot, setActiveSnapshot] = useState<TaskSpaceSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [takeoverLoadingId, setTakeoverLoadingId] = useState<string | null>(null);

  const loadSpaces = useCallback(async () => {
    try {
      const list = await fetchTaskSpaces();
      setSpaces(list);
    } catch {
      // Ignore background poll errors
    }
  }, []);

  useEffect(() => {
    void loadSpaces();
    if (autoRefreshIntervalMs <= 0) return;

    // Adaptive polling: relax interval when empty to conserve network & battery,
    // resume high-frequency poll when spaces are active or dock is expanded.
    const effectiveInterval =
      spaces.length === 0 && !isExpanded
        ? Math.max(autoRefreshIntervalMs * 2, 10000)
        : autoRefreshIntervalMs;

    const timer = setInterval(() => {
      void loadSpaces();
    }, effectiveInterval);
    return () => clearInterval(timer);
  }, [loadSpaces, autoRefreshIntervalMs, spaces.length, isExpanded]);

  const handleToggleTakeover = async (space: TaskSpaceInfo) => {
    setTakeoverLoadingId(space.space_id);
    try {
      const updated = await toggleTaskSpaceTakeover(space.space_id, !space.takeover_active);
      setSpaces((prev) =>
        prev.map((s) => (s.space_id === updated.space_id ? updated : s)),
      );
    } finally {
      setTakeoverLoadingId(null);
    }
  };

  const handleClose = async (spaceId: string) => {
    await closeTaskSpace(spaceId);
    setSpaces((prev) => prev.filter((s) => s.space_id !== spaceId));
    if (activeSnapshot?.space_id === spaceId) {
      setActiveSnapshot(null);
    }
  };

  const handlePreview = async (spaceId: string) => {
    setIsLoading(true);
    try {
      const snapshot = await fetchTaskSpaceSnapshot(spaceId);
      setActiveSnapshot(snapshot);
    } finally {
      setIsLoading(false);
    }
  };

  // If there are no active spaces, render nothing to keep workspace clean
  if (spaces.length === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        'fixed z-50 transition-all duration-200 select-none',
        // Responsive position: bottom-center on mobile with safe-area support, bottom-right on desktop
        'bottom-[calc(1rem+env(safe-area-inset-bottom,0px))] right-4 sm:right-6 sm:bottom-6 max-w-[calc(100vw-2rem)] sm:max-w-md',
        className,
      )}
    >
      {/* Minimized Floating Pill */}
      {!isExpanded ? (
        <button
          type="button"
          onClick={() => setIsExpanded(true)}
          className={cn(
            'flex items-center gap-2.5 px-4 py-2.5 rounded-full shadow-lg backdrop-blur-md',
            'border border-primary/20 bg-background/90 text-foreground',
            'hover:bg-primary/10 hover:border-primary/40 transition-colors',
            'text-xs font-medium cursor-pointer',
          )}
        >
          <Layers className="w-4 h-4 text-primary animate-pulse" />
          <span>{t('title')}</span>
          <span className="inline-flex items-center justify-center px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-primary text-primary-foreground">
            {spaces.length}
          </span>
          <ChevronUp className="w-3.5 h-3.5 text-muted-foreground ml-1" />
        </button>
      ) : (
        /* Expanded Floating Card */
        <div
          className={cn(
            'flex flex-col w-full sm:w-[380px] rounded-2xl shadow-2xl backdrop-blur-xl',
            'border border-border/60 bg-card/95 text-card-foreground overflow-hidden',
            'animate-in fade-in-50 zoom-in-95 duration-150',
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/40 bg-muted/30">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary" />
              <h4 className="text-sm font-semibold tracking-tight">{t('title')}</h4>
              <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-primary/15 text-primary">
                {spaces.length}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => void loadSpaces()}
                title="Refresh"
                className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
              </button>
              <button
                type="button"
                onClick={() => setIsExpanded(false)}
                className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* List of Spaces */}
          <div className="flex flex-col gap-2 p-3 max-h-72 overflow-y-auto">
            {spaces.map((space) => {
              const isTakeover = space.takeover_active;
              return (
                <div
                  key={space.space_id}
                  className={cn(
                    'flex flex-col gap-2 p-3 rounded-xl border transition-all text-xs',
                    isTakeover
                      ? 'border-amber-500/40 bg-amber-500/5'
                      : 'border-border/50 bg-background/50 hover:border-border',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="font-semibold truncate text-foreground">
                        {space.name || space.space_id}
                      </span>
                      {isTakeover ? (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/20 text-amber-500 flex items-center gap-1">
                          <UserCheck className="w-2.5 h-2.5" />
                          {t('badgeTakeover')}
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/20 text-emerald-500 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          {t('badgeRunning')}
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleClose(space.space_id)}
                      title={t('closeSpaceBtn')}
                      className="text-muted-foreground hover:text-destructive transition-colors p-0.5 cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Subtext info */}
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="truncate max-w-[200px]" title={space.current_url || 'about:blank'}>
                      {space.current_url ? (
                        <span className="flex items-center gap-1">
                          <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                          {space.current_title || space.current_url}
                        </span>
                      ) : (
                        t('activePages', { count: space.active_pages })
                      )}
                    </span>
                    <span>{space.idle_seconds}s idle</span>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 mt-1 pt-2 border-t border-border/30">
                    <button
                      type="button"
                      onClick={() => handleToggleTakeover(space)}
                      disabled={takeoverLoadingId === space.space_id}
                      className={cn(
                        'flex-1 flex items-center justify-center gap-1 py-1 px-2 rounded-md font-medium text-[11px] transition-colors cursor-pointer',
                        isTakeover
                          ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                          : 'bg-muted text-foreground hover:bg-muted/80',
                      )}
                    >
                      {isTakeover ? (
                        <>
                          <Bot className="w-3 h-3" />
                          {t('releaseTakeoverBtn')}
                        </>
                      ) : (
                        <>
                          <UserCheck className="w-3 h-3" />
                          {t('takeoverBtn')}
                        </>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={() => handlePreview(space.space_id)}
                      className="p-1 px-2 rounded-md bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center gap-1 cursor-pointer"
                      title={t('snapshotPreview')}
                    >
                      <Eye className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Snapshot Modal / Popover */}
          {activeSnapshot && (
            <div className="p-3 border-t border-border/40 bg-background/80 flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs font-medium">
                <span className="text-muted-foreground">{t('snapshotPreview')}</span>
                <button
                  type="button"
                  onClick={() => setActiveSnapshot(null)}
                  className="text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              {activeSnapshot.screenshot_jpeg_b64 ? (
                <img
                  src={`data:image/jpeg;base64,${activeSnapshot.screenshot_jpeg_b64}`}
                  alt="TaskSpace Snapshot"
                  className="w-full rounded-lg border border-border/60 max-h-48 object-cover object-top"
                />
              ) : (
                <div className="w-full py-6 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                  {t('emptyState')}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
