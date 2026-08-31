'use client';

/**
 * [INPUT]
 * - @/services/projects::updateProject
 * - @/services/chat::browseDirectories
 * - @tauri-apps/plugin-dialog (Tauri folder picker)
 *
 * [OUTPUT]
 * - ProjectWorkspaceMount: folder bind UI for a project workspace
 *
 * [POS]
 * GUI-first project workspace binding. Replaces manual path typing with
 * native folder picker (Tauri) or server browse popover (Web/Local).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FolderOpen, FolderClosed, ChevronRight, ArrowLeft, Check, X, Clock } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { browseDirectories, type DirectoryEntry } from '@/services/chat';
import { updateProject } from '@/services/projects';
import {
  getRecentDirectoryPaths,
  PROJECT_WORKSPACE_RECENT_KEY,
  rememberDirectoryPath,
  shortenHomePath,
} from '@/lib/directoryBrowseRecent';
import { toast } from '@/hooks/shared/useToast';
import { isTauriEnvironment } from '@/lib/tauri';
import WorkspaceTrustFolderGate from './WorkspaceTrustFolderGate';

function addRecentDir(dir: string): void {
  rememberDirectoryPath(PROJECT_WORKSPACE_RECENT_KEY, dir);
}

export interface ProjectWorkspaceMountProps {
  projectId: string;
  projectName: string;
  initialPath?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onBound: (workspacePath: string | null) => void;
  className?: string;
}

export default function ProjectWorkspaceMount({
  projectId,
  projectName,
  initialPath,
  open,
  onOpenChange,
  onBound,
  className,
}: ProjectWorkspaceMountProps) {
  const t = useTranslations('project.workspaceMount');
  const [browseOpen, setBrowseOpen] = useState(false);
  const [currentPath, setCurrentPath] = useState<string>(initialPath ?? '');
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pathInput, setPathInput] = useState('');
  const [filterQuery, setFilterQuery] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [gateOpen, setGateOpen] = useState(false);
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const loadGenRef = useRef(0);

  useEffect(() => {
    if (open) {
      setCurrentPath(initialPath ?? '');
      setPathInput(initialPath ?? '');
    }
  }, [open, initialPath]);

  const finalizeWorkspaceBind = useCallback(
    async (dir: string | null) => {
      setSubmitting(true);
      try {
        const project = await updateProject(projectId, { workspace_path: dir ?? '' });
        const bound = project.workspacePath ?? null;
        if (bound) {
          addRecentDir(bound);
        }
        toast({ title: bound ? t('updated') : t('cleared') });
        onBound(bound);
        onOpenChange(false);
        setBrowseOpen(false);
      } catch {
        toast({ title: t('invalidPath'), variant: 'destructive' });
      } finally {
        setSubmitting(false);
      }
    },
    [onBound, onOpenChange, projectId, t],
  );

  const persistWorkspace = useCallback(
    async (dir: string | null) => {
      if (dir === null) {
        await finalizeWorkspaceBind(null);
        return;
      }
      setPendingPath(dir);
      setGateOpen(true);
    },
    [finalizeWorkspaceBind],
  );

  const handleGateDecided = useCallback(
    async (path: string, _level: 'TRUSTED' | 'RESTRICTED') => {
      await finalizeWorkspaceBind(path);
      setPendingPath(null);
    },
    [finalizeWorkspaceBind],
  );

  const loadDirectory = useCallback(
    async (path: string) => {
      const gen = ++loadGenRef.current;
      setLoading(true);
      setFilterQuery('');
      try {
        const result = await browseDirectories(path);
        if (gen !== loadGenRef.current) {
          return;
        }
        setEntries(result.entries);
        setCurrentPath(result.current);
        setParentPath(result.parent);
        setPathInput(result.current);
      } catch {
        if (gen !== loadGenRef.current) {
          return;
        }
        toast({ title: t('invalidPath'), variant: 'destructive' });
      } finally {
        if (gen === loadGenRef.current) {
          setLoading(false);
        }
      }
    },
    [t],
  );

  useEffect(() => {
    if (browseOpen) {
      void loadDirectory(currentPath || '~');
    }
  }, [browseOpen, currentPath, loadDirectory]);

  const filteredEntries = useMemo(() => {
    if (!filterQuery.trim()) {
      return entries;
    }
    const q = filterQuery.toLowerCase();
    return entries.filter((e) => e.name.toLowerCase().includes(q));
  }, [entries, filterQuery]);

  const handleTauriNativePicker = useCallback(async () => {
    try {
      const { open: openDialog } = await import('@tauri-apps/plugin-dialog');
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: t('pickFolderTitle', { name: projectName }),
        defaultPath: currentPath || undefined,
      });
      if (!selected) {
        return;
      }
      const dir = typeof selected === 'string' ? selected : selected[0];
      await persistWorkspace(dir);
    } catch {
      setBrowseOpen(true);
    }
  }, [currentPath, persistWorkspace, projectName, t]);

  const handlePrimaryPick = useCallback(async () => {
    if (isTauriEnvironment()) {
      await handleTauriNativePicker();
      return;
    }
    setBrowseOpen(true);
  }, [handleTauriNativePicker]);

  const recentDirs = getRecentDirectoryPaths(PROJECT_WORKSPACE_RECENT_KEY);

  if (!open) {
    return null;
  }

  return (
    <div className={cn('mt-1 rounded-lg border border-border/60 bg-card/80 p-2 space-y-2 shadow-sm', className)}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-foreground">{t('title')}</div>
          <div className="text-[10px] text-muted-foreground truncate">{projectName}</div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          onClick={() => onOpenChange(false)}
          aria-label={t('close')}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {currentPath ? (
        <div className="flex items-center gap-1.5 rounded-md bg-muted/40 px-2 py-1 text-[10px] text-muted-foreground">
          <FolderOpen className="h-3 w-3 shrink-0 text-primary/70" />
          <span className="truncate">{shortenHomePath(currentPath)}</span>
        </div>
      ) : (
        <p className="text-[10px] text-muted-foreground leading-relaxed">{t('emptyHint')}</p>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <Button size="sm" className="h-7 text-xs" disabled={submitting} onClick={() => void handlePrimaryPick()}>
          {t('chooseFolder')}
        </Button>
        {currentPath && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={submitting}
            onClick={() => void persistWorkspace(null)}
          >
            {t('clear')}
          </Button>
        )}
      </div>

      <Popover open={browseOpen} onOpenChange={setBrowseOpen}>
        <PopoverTrigger asChild>
          <span className="sr-only">{t('browseTrigger')}</span>
        </PopoverTrigger>
        <PopoverContent className="w-80 p-0" align="start">
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 border-b px-2 py-1.5">
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
              <Input
                value={pathInput}
                onChange={(e) => setPathInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && pathInput.trim()) {
                    e.preventDefault();
                    void loadDirectory(pathInput.trim());
                  }
                }}
                className="h-6 flex-1 border-none bg-transparent px-1 text-xs shadow-none focus-visible:ring-0"
                placeholder={t('pathPlaceholder')}
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 text-primary"
                disabled={submitting || !currentPath}
                onClick={() => void persistWorkspace(currentPath)}
                title={t('selectThis')}
              >
                <Check className="h-3.5 w-3.5" />
              </Button>
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
                    onClick={() => void persistWorkspace(dir)}
                  >
                    <FolderOpen className="h-3 w-3 shrink-0 text-primary/60" />
                    <span className="truncate">{shortenHomePath(dir)}</span>
                  </button>
                ))}
              </div>
            )}

            {entries.length > 8 && !loading && (
              <div className="border-b px-2 py-1">
                <Input
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                  className="h-6 border-none bg-muted/30 px-2 text-xs shadow-none focus-visible:ring-0"
                  placeholder={t('filter')}
                />
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
          </div>
        </PopoverContent>
      </Popover>

      <WorkspaceTrustFolderGate
        open={gateOpen}
        folderPath={pendingPath}
        onOpenChange={setGateOpen}
        onDecided={handleGateDecided}
      />
    </div>
  );
}
