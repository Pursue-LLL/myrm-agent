'use client';

/**
 * [INPUT]
 * - @/store/useChatStore (POS: Global chat store for workspaceDir, sandboxMode, actionMode)
 * - @/services/chat::mkdirInWorkspace, browseDirectories, updateChatWorkspaceDir
 * - @/lib/tauri::isTauriEnvironment
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - NewTaskWorkContextCard (UnifiedWorkContextCard): Unified onboarding card in EmptyChat
 *   for mode selection (Local Workspace / Cloud Sandbox / Quick Chat) and office directory scaffolding.
 *
 * [POS]
 * EmptyChat center workspace context card. Bridges user intention with execution
 * boundaries, allowing instant local folder binding, cloud sandbox isolation, and standard
 * office directory scaffolding (00_原始资料/ 01_参考/ 02_生成结果/ 03_历史版本).
 */

import React, { memo, useCallback, useState, useMemo, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import {
  FolderOpen,
  FolderClosed,
  Boxes,
  MessageSquare,
  FolderPlus,
  Check,
  X,
  Sparkles,
  Layers,
  ChevronRight,
  HardDrive,
  Clock,
  ArrowLeft,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Input } from '@/components/primitives/input';
import useChatStore from '@/store/useChatStore';
import { isTauriEnvironment } from '@/lib/tauri';
import { mkdirInWorkspace, browseDirectories, updateChatWorkspaceDir, type DirectoryEntry } from '@/services/chat';
import { toast } from '@/hooks/shared/useToast';

export type NewTaskMode = 'local' | 'cloud' | 'chat';

const RECENT_DIRS_KEY = 'myrm.workspaceDirPicker.recent';
const MAX_RECENT_DIRS = 5;

function getRecentDirs(): string[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = localStorage.getItem(RECENT_DIRS_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item): item is string => typeof item === 'string').slice(0, MAX_RECENT_DIRS);
  } catch {
    return [];
  }
}

function addRecentDir(dir: string): void {
  const current = getRecentDirs().filter((d) => d !== dir);
  const updated = [dir, ...current].slice(0, MAX_RECENT_DIRS);
  localStorage.setItem(RECENT_DIRS_KEY, JSON.stringify(updated));
}

const STANDARD_OFFICE_FOLDERS = ['00_原始资料', '01_参考', '02_生成结果', '03_历史版本'] as const;

interface NewTaskWorkContextCardProps {
  className?: string;
}

export const NewTaskWorkContextCard = memo(function NewTaskWorkContextCard({ className }: NewTaskWorkContextCardProps) {
  const t = useTranslations('chat.newTaskCard');
  const tDir = useTranslations('chat.workspaceDir');

  const chatId = useChatStore((s) => s.chatId);
  const workspaceDir = useChatStore((s) => s.workspaceDir);
  const setWorkspaceDir = useChatStore((s) => s.setWorkspaceDir);
  const actionMode = useChatStore((s) => s.actionMode);
  const setActionMode = useChatStore((s) => s.setActionMode);
  const sandboxMode = useChatStore((s) => s.sandboxMode);
  const setSandboxMode = useChatStore((s) => s.setSandboxMode);

  // Derive active mode based on current store state
  const currentMode: NewTaskMode = useMemo(() => {
    if (sandboxMode) return 'cloud';
    if (workspaceDir || actionMode === 'agent') return 'local';
    return 'chat';
  }, [sandboxMode, workspaceDir, actionMode]);

  const [isScaffolding, setIsScaffolding] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [currentBrowsePath, setCurrentBrowsePath] = useState('');
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [pathInput, setPathInput] = useState('');
  const [filterQuery, setFilterQuery] = useState('');
  const [loadingDir, setLoadingDir] = useState(false);
  const loadGenRef = useRef(0);

  // Switch between execution modes
  const handleModeChange = useCallback(
    (mode: NewTaskMode) => {
      if (mode === 'local') {
        setSandboxMode(false);
        setActionMode('agent');
      } else if (mode === 'cloud') {
        setSandboxMode(true);
        setActionMode('agent');
      } else {
        setSandboxMode(false);
        setActionMode('fast');
        setWorkspaceDir(null);
        if (chatId) {
          void updateChatWorkspaceDir(chatId, null);
        }
      }
    },
    [chatId, setActionMode, setSandboxMode, setWorkspaceDir],
  );

  // Directory navigation for WebUI popover
  const loadDirectory = useCallback(
    async (path: string) => {
      const gen = ++loadGenRef.current;
      setLoadingDir(true);
      setFilterQuery('');
      try {
        const result = await browseDirectories(path);
        if (gen !== loadGenRef.current) return;
        setEntries(result.entries);
        setCurrentBrowsePath(result.current);
        setParentPath(result.parent);
        setPathInput(result.current);
      } catch {
        if (gen !== loadGenRef.current) return;
        toast({ title: tDir('invalidPath'), variant: 'destructive' });
      } finally {
        if (gen === loadGenRef.current) {
          setLoadingDir(false);
        }
      }
    },
    [tDir],
  );

  useEffect(() => {
    if (pickerOpen) {
      loadDirectory(workspaceDir || '~');
    }
  }, [pickerOpen, loadDirectory, workspaceDir]);

  // Apply selected directory to chat store and backend
  const applyDirectory = useCallback(
    async (dir: string | null) => {
      setWorkspaceDir(dir);
      if (chatId) {
        try {
          await updateChatWorkspaceDir(chatId, dir);
        } catch {
          // Non-blocking for offline or pre-chat states
        }
      }
      if (dir) {
        addRecentDir(dir);
        setActionMode('agent');
        setSandboxMode(false);
        toast({ title: tDir('updated') });
      } else {
        toast({ title: tDir('cleared') });
      }
      setPickerOpen(false);
    },
    [chatId, setActionMode, setSandboxMode, setWorkspaceDir, tDir],
  );

  // Native OS dialog picker for Tauri desktop
  const handleTauriPicker = useCallback(async () => {
    try {
      const { open: openDialog } = await import('@tauri-apps/plugin-dialog');
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: t('bindWorkspace'),
        defaultPath: workspaceDir || undefined,
      });
      if (selected) {
        const dir = typeof selected === 'string' ? selected : selected[0];
        await applyDirectory(dir);
      }
    } catch {
      setPickerOpen(true);
      loadDirectory(workspaceDir || '~');
    }
  }, [applyDirectory, loadDirectory, t, workspaceDir]);

  // Open directory picker (Tauri native or WebUI popover)
  const handleOpenPicker = useCallback(() => {
    if (isTauriEnvironment()) {
      void handleTauriPicker();
    } else {
      setPickerOpen(true);
    }
  }, [handleTauriPicker]);

  // One-click standard office scaffolding creation
  const handleCreateScaffold = useCallback(async () => {
    if (!workspaceDir) {
      toast({ title: t('noWorkspaceSelected'), variant: 'destructive' });
      return;
    }
    setIsScaffolding(true);
    try {
      const results = await Promise.allSettled(
        STANDARD_OFFICE_FOLDERS.map((folder) => mkdirInWorkspace(workspaceDir, folder)),
      );
      const failures = results.filter((r) => r.status === 'rejected');
      if (failures.length === 0 || failures.length < STANDARD_OFFICE_FOLDERS.length) {
        toast({ title: t('scaffoldSuccess') });
      } else {
        toast({ title: t('scaffoldFailed'), variant: 'destructive' });
      }
    } catch {
      toast({ title: t('scaffoldFailed'), variant: 'destructive' });
    } finally {
      setIsScaffolding(false);
    }
  }, [t, workspaceDir]);

  const filteredEntries = useMemo(() => {
    if (!filterQuery.trim()) {
      return entries;
    }
    const q = filterQuery.toLowerCase();
    return entries.filter((e) => e.name.toLowerCase().includes(q));
  }, [entries, filterQuery]);

  const recentDirs = getRecentDirs();
  const shortenPath = (p: string) => p.replace(/^\/(?:Users|home)\/[^/]+/, '~');

  return (
    <div
      data-testid="new-task-work-context-card"
      className={cn(
        'w-full max-w-screen-md lg:max-w-[820px] mx-auto rounded-2xl border border-border/60 bg-card/60 backdrop-blur-md p-3 sm:p-4 shadow-xs transition-all duration-200 hover:border-primary/30',
        className,
      )}
    >
      {/* Mode Switcher Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-border/40">
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-muted/50 text-xs font-medium">
          <button
            type="button"
            data-testid="context-mode-local"
            onClick={() => handleModeChange('local')}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all',
              currentMode === 'local'
                ? 'bg-background text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <HardDrive className="h-3.5 w-3.5 text-primary" />
            <span>{t('modeLocal')}</span>
          </button>

          <button
            type="button"
            data-testid="context-mode-cloud"
            onClick={() => handleModeChange('cloud')}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all',
              currentMode === 'cloud'
                ? 'bg-background text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Boxes className="h-3.5 w-3.5 text-blue-500" />
            <span>{t('modeCloud')}</span>
          </button>

          <button
            type="button"
            data-testid="context-mode-chat"
            onClick={() => handleModeChange('chat')}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all',
              currentMode === 'chat'
                ? 'bg-background text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <MessageSquare className="h-3.5 w-3.5 text-emerald-500" />
            <span>{t('modeChat')}</span>
          </button>
        </div>

        {/* Mode description hint */}
        <span className="hidden md:inline-block text-[11px] text-muted-foreground truncate max-w-[280px]">
          {currentMode === 'local' && t('modeLocalDesc')}
          {currentMode === 'cloud' && t('modeCloudDesc')}
          {currentMode === 'chat' && t('modeChatDesc')}
        </span>
      </div>

      {/* Context Action Area */}
      {currentMode === 'local' && (
        <div className="pt-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2.5">
          {/* Workspace Path Display & Picker */}
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  data-testid="workspace-picker-trigger"
                  onClick={handleOpenPicker}
                  className={cn(
                    'h-8 px-2.5 text-xs font-normal gap-1.5 max-w-full justify-start rounded-lg border-dashed',
                    workspaceDir
                      ? 'border-primary/40 bg-primary/5 text-foreground'
                      : 'border-border text-muted-foreground',
                  )}
                >
                  <FolderOpen
                    className={cn('h-3.5 w-3.5 shrink-0', workspaceDir ? 'text-primary' : 'text-muted-foreground')}
                  />
                  <span className="truncate max-w-[220px] sm:max-w-[320px]">
                    {workspaceDir ? shortenPath(workspaceDir) : t('noWorkspaceSelected')}
                  </span>
                </Button>
              </PopoverTrigger>

              <PopoverContent className="w-80 p-0" align="start">
                <div className="flex flex-col text-xs">
                  <div className="flex items-center gap-1.5 border-b px-2 py-1.5">
                    {parentPath && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={() => loadDirectory(parentPath)}
                      >
                        <ArrowLeft className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Input
                      value={pathInput}
                      onChange={(e) => setPathInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && pathInput.trim()) {
                          e.preventDefault();
                          loadDirectory(pathInput.trim());
                        }
                      }}
                      className="h-6 flex-1 border-none bg-transparent px-1 text-xs shadow-none focus-visible:ring-0"
                      placeholder={tDir('placeholder')}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0 text-primary"
                      onClick={() => applyDirectory(currentBrowsePath || pathInput.trim())}
                      title={tDir('selectThis')}
                    >
                      <Check className="h-3.5 w-3.5" />
                    </Button>
                    {workspaceDir && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0 text-destructive"
                        onClick={() => applyDirectory(null)}
                        title={tDir('clear')}
                      >
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>

                  {/* Recent directories */}
                  {recentDirs.length > 0 && !loadingDir && (
                    <div className="border-b px-2 py-1.5">
                      <div className="mb-1 flex items-center gap-1 text-[10px] font-medium uppercase text-muted-foreground">
                        <Clock className="h-2.5 w-2.5" />
                        {tDir('recent')}
                      </div>
                      {recentDirs.map((dir) => (
                        <button
                          key={dir}
                          type="button"
                          className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs hover:bg-accent/50 transition-colors"
                          onClick={() => applyDirectory(dir)}
                        >
                          <FolderOpen className="h-3 w-3 shrink-0 text-primary/60" />
                          <span className="truncate">{shortenPath(dir)}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Filter input */}
                  {entries.length > 8 && !loadingDir && (
                    <div className="border-b px-2 py-1">
                      <Input
                        value={filterQuery}
                        onChange={(e) => setFilterQuery(e.target.value)}
                        className="h-6 border-none bg-muted/30 px-2 text-xs shadow-none focus-visible:ring-0"
                        placeholder={tDir('filter')}
                      />
                    </div>
                  )}

                  <div className="max-h-48 overflow-y-auto p-1">
                    {loadingDir ? (
                      <div className="flex items-center justify-center py-4">
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                      </div>
                    ) : filteredEntries.length === 0 ? (
                      <div className="py-4 text-center text-xs text-muted-foreground">{tDir('noSubdirs')}</div>
                    ) : (
                      filteredEntries.map((entry) => (
                        <button
                          key={entry.path}
                          type="button"
                          onClick={() => loadDirectory(entry.path)}
                          className="flex w-full items-center justify-between rounded px-2 py-1 text-left hover:bg-muted"
                        >
                          <div className="flex items-center gap-1.5 truncate">
                            <FolderClosed className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                            <span className="truncate">{entry.name}</span>
                          </div>
                          <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                        </button>
                      ))
                    )}
                  </div>
                </div>
              </PopoverContent>
            </Popover>

            {workspaceDir && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => applyDirectory(null)}
                className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0"
                title={t('clearWorkspace')}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>

          {/* Scaffold Action */}
          {workspaceDir && (
            <Button
              variant="secondary"
              size="sm"
              disabled={isScaffolding}
              data-testid="scaffold-btn"
              onClick={handleCreateScaffold}
              className="h-8 px-2.5 text-xs font-medium gap-1.5 shrink-0 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20"
              title={t('scaffoldTooltip')}
            >
              <FolderPlus className="h-3.5 w-3.5" />
              <span>{t('scaffoldBtn')}</span>
            </Button>
          )}
        </div>
      )}

      {currentMode === 'cloud' && (
        <div className="pt-3 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="size-2 rounded-full bg-blue-500 animate-pulse" />
            <span>{t('modeCloudDesc')}</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-primary/80 font-medium">
            <Layers className="h-3 w-3" />
            <span>Dedicated Sandbox Volume</span>
          </div>
        </div>
      )}

      {currentMode === 'chat' && (
        <div className="pt-3 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
            <span>{t('modeChatDesc')}</span>
          </div>
        </div>
      )}
    </div>
  );
});

NewTaskWorkContextCard.displayName = 'NewTaskWorkContextCard';

export const UnifiedWorkContextCard = NewTaskWorkContextCard;

export default NewTaskWorkContextCard;
