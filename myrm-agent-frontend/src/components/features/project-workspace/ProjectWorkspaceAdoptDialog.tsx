'use client';

/**
 * [INPUT]
 * - @/store/useProjectStore::useProjectStore
 * - @/store/useChatStore::useChatStore
 * - @/services/chat::browseDirectories
 * - @tauri-apps/plugin-dialog (Tauri folder picker)
 *
 * [OUTPUT]
 * - ProjectWorkspaceAdoptDialog: UI for zero-friction folder adoption as a Myrm Project
 *
 * [POS]
 * Project workspace adopt dialog. Transforms external folders into Myrm Projects with
 * automatic workspace_path binding and active filter synchronization.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FolderOpen, FolderClosed, ChevronRight, ArrowLeft, Check, X, Clock, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { browseDirectories, type DirectoryEntry } from '@/services/chat';
import { useProjectStore } from '@/store/useProjectStore';
import useChatStore from '@/store/useChatStore';
import {
  getRecentDirectoryPaths,
  PROJECT_WORKSPACE_RECENT_KEY,
  rememberDirectoryPath,
  shortenHomePath,
} from '@/lib/directoryBrowseRecent';
import { toast } from '@/hooks/shared/useToast';
import { isTauriEnvironment } from '@/lib/tauri';

function addRecentDir(dir: string): void {
  rememberDirectoryPath(PROJECT_WORKSPACE_RECENT_KEY, dir);
}

export interface ProjectWorkspaceAdoptDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialPath?: string | null;
  className?: string;
}

export default function ProjectWorkspaceAdoptDialog({
  open,
  onOpenChange,
  initialPath,
  className,
}: ProjectWorkspaceAdoptDialogProps) {
  const t = useTranslations('project.workspaceMount');
  const adoptProject = useProjectStore((s) => s.adoptProject);
  const chatId = useChatStore((s) => s.chatId);
  const setWorkspaceDir = useChatStore((s) => s.setWorkspaceDir);

  const [browseOpen, setBrowseOpen] = useState(false);
  const [currentPath, setCurrentPath] = useState<string>(initialPath ?? '');
  const [projectName, setProjectName] = useState<string>('');
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [filterQuery, setFilterQuery] = useState('');
  const loadGenRef = useRef(0);

  const recentDirs = useMemo(() => getRecentDirectoryPaths(PROJECT_WORKSPACE_RECENT_KEY), [browseOpen]);

  useEffect(() => {
    if (open && initialPath) {
      setCurrentPath(initialPath);
      const extracted = initialPath.split(/[/\\]/).filter(Boolean).pop() || '';
      setProjectName(extracted);
    }
  }, [open, initialPath]);

  const loadDirectory = useCallback(
    async (path?: string) => {
      const gen = ++loadGenRef.current;
      setLoading(true);
      try {
        const data = await browseDirectories(path);
        if (gen !== loadGenRef.current) return;
        setCurrentPath(data.current_path);
        setParentPath(data.parent_path);
        setEntries(data.entries ?? []);
        setFilterQuery('');
        const extracted = data.current_path.split(/[/\\]/).filter(Boolean).pop() || '';
        setProjectName((prev) => (prev ? prev : extracted));
      } catch {
        if (gen !== loadGenRef.current) return;
        toast({
          title: t('loadFailed'),
          variant: 'destructive',
        });
      } finally {
        if (gen === loadGenRef.current) {
          setLoading(false);
        }
      }
    },
    [t],
  );

  const handleNativePick = useCallback(async () => {
    if (!isTauriEnvironment()) return;
    try {
      const { open: openDialog } = await import('@tauri-apps/plugin-dialog');
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: t('title'),
      });
      if (typeof selected === 'string' && selected) {
        setCurrentPath(selected);
        const extracted = selected.split(/[/\\]/).filter(Boolean).pop() || '';
        setProjectName((prev) => (prev ? prev : extracted));
      }
    } catch (error) {
      console.warn('Native folder pick failed, falling back:', error);
      setBrowseOpen(true);
      void loadDirectory(currentPath || undefined);
    }
  }, [currentPath, loadDirectory, t]);

  const handleOpenBrowse = useCallback(
    (isOpen: boolean) => {
      setBrowseOpen(isOpen);
      if (isOpen && entries.length === 0) {
        void loadDirectory(currentPath || undefined);
      }
    },
    [currentPath, entries.length, loadDirectory],
  );

  const handleAdopt = useCallback(async () => {
    if (!currentPath.trim()) return;
    setSubmitting(true);
    try {
      const project = await adoptProject(currentPath.trim(), projectName.trim() || undefined);
      addRecentDir(currentPath.trim());
      if (chatId) {
        setWorkspaceDir(currentPath.trim());
      }
      toast({
        title: t('boundSuccess'),
      });
      onOpenChange(false);
    } catch (error) {
      toast({
        title: t('bindFailed'),
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  }, [currentPath, projectName, adoptProject, chatId, setWorkspaceDir, t, onOpenChange]);

  const filteredEntries = useMemo(() => {
    if (!filterQuery.trim()) return entries;
    const q = filterQuery.toLowerCase();
    return entries.filter((e) => e.name.toLowerCase().includes(q));
  }, [entries, filterQuery]);

  if (!open) return null;

  return (
    <div
      className={cn('fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm', className)}
    >
      <div className="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">{t('title')}</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">{t('currentPath')}</label>
            <div className="mt-1 flex gap-2">
              <Input
                value={currentPath}
                onChange={(e) => {
                  setCurrentPath(e.target.value);
                  const extracted = e.target.value.split(/[/\\]/).filter(Boolean).pop() || '';
                  setProjectName((prev) => (prev ? prev : extracted));
                }}
                placeholder={t('pathPlaceholder')}
                className="text-sm font-mono"
              />
              {isTauriEnvironment() ? (
                <Button variant="outline" size="icon" onClick={() => void handleNativePick()}>
                  <FolderOpen className="h-4 w-4" />
                </Button>
              ) : (
                <Popover open={browseOpen} onOpenChange={handleOpenBrowse}>
                  <PopoverTrigger asChild>
                    <Button variant="outline" size="icon">
                      <FolderOpen className="h-4 w-4" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-80 p-0" align="end">
                    <div className="flex items-center justify-between border-b px-3 py-2">
                      <div className="flex items-center gap-1 min-w-0">
                        {parentPath && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 shrink-0"
                            onClick={() => void loadDirectory(parentPath)}
                          >
                            <ArrowLeft className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <span className="truncate text-xs font-mono">{shortenHomePath(currentPath)}</span>
                      </div>
                    </div>
                    {recentDirs.length > 0 && !loading && (
                      <div className="border-b px-2 py-1.5">
                        <div className="mb-1 flex items-center gap-1 text-[10px] font-medium uppercase text-muted-foreground">
                          <Clock className="h-2.5 w-2.5" />
                          {t('recent')}
                        </div>
                        {recentDirs.map((dir) => (
                          <button
                            key={dir}
                            type="button"
                            className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs hover:bg-accent/50 transition-colors"
                            onClick={() => {
                              setCurrentPath(dir);
                              const extracted = dir.split(/[/\\]/).filter(Boolean).pop() || '';
                              setProjectName((prev) => (prev ? prev : extracted));
                              setBrowseOpen(false);
                            }}
                          >
                            <FolderOpen className="h-3 w-3 shrink-0 text-primary/60" />
                            <span className="truncate">{shortenHomePath(dir)}</span>
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="max-h-52 overflow-y-auto">
                      {loading ? (
                        <div className="flex items-center justify-center py-6">
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                        </div>
                      ) : filteredEntries.length === 0 ? (
                        <div className="py-6 text-center text-xs text-muted-foreground">{t('noSubdirs')}</div>
                      ) : (
                        filteredEntries.map((entry) => (
                          <button
                            key={entry.path}
                            type="button"
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent/50 transition-colors"
                            onClick={() => void loadDirectory(entry.path)}
                          >
                            <FolderClosed className="h-4 w-4 shrink-0 text-muted-foreground" />
                            <span className="truncate">{entry.name}</span>
                            <ChevronRight className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                          </button>
                        ))
                      )}
                    </div>
                  </PopoverContent>
                </Popover>
              )}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground">项目名称</label>
            <Input
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="项目名称"
              className="mt-1 text-sm"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={() => void handleAdopt()} disabled={submitting || !currentPath.trim()}>
            {submitting ? '正在接纳...' : '立即接纳项目'}
          </Button>
        </div>
      </div>
    </div>
  );
}
