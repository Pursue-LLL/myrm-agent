'use client';

/**
 * [INPUT]
 * - @/services/chat::browseDirectories, mkdirInWorkspace, updateChatWorkspaceDir (POS: workspace directory API)
 * - @/store/useChatStore (POS: workspaceDir / chatId / actionMode)
 * - @/lib/desktopBridge (POS: native folder dialog on desktop)
 * - @/lib/api::ApiError (POS: 404 means the chat row appears on the first message)
 * - @/lib/workspacePathIssue::workspacePathIssueMessageKey (POS: shared reading of a backend folder refusal)
 *
 * [OUTPUT]
 * - WorkspaceDirPicker: the single "where does this chat work" control, one row under the composer
 *
 * [POS]
 * The only place a viewer binds, changes or clears the folder a chat works in, on every viewport.
 * A folder picked before the chat exists travels with the first message instead of being saved
 * immediately, so the row never fails silently on a new chat.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  FolderOpen,
  FolderClosed,
  FolderPlus,
  ChevronRight,
  ChevronDown,
  ArrowLeft,
  X,
  Check,
  Clock,
  Loader2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { browseDirectories, mkdirInWorkspace, updateChatWorkspaceDir, type DirectoryEntry } from '@/services/chat';
import { toast } from '@/hooks/shared/useToast';
import useChatStore from '@/store/useChatStore';
import { desktopBridge } from '@/lib/desktopBridge';
import { ApiError } from '@/lib/api';
import { workspacePathIssueMessageKey } from '@/lib/workspacePathIssue';
import {
  WORKSPACE_PICKER_RECENT_KEY,
  getRecentDirectoryPaths,
  rememberDirectoryPath,
  shortenHomePath,
} from '@/lib/directoryBrowseRecent';

// The scaffold finds the folders it already created by name, so the names are not localized: a language
// switch would otherwise create a second set next to the first.
const OFFICE_FOLDERS = ['00_原始资料', '01_参考', '02_生成结果', '03_历史版本'] as const;

const rememberDir = (dir: string): void => rememberDirectoryPath(WORKSPACE_PICKER_RECENT_KEY, dir);

/** Keep the leaf visible when the full path does not fit: `~/a/b/c` becomes `…/b/c`. */
function compactPath(path: string): string {
  const home = shortenHomePath(path);
  const parts = home.split(/[\\/]/).filter(Boolean);
  return parts.length <= 3 ? home : `…/${parts.slice(-2).join('/')}`;
}

interface WorkspaceDirPickerProps {
  className?: string;
}

export default function WorkspaceDirPicker({ className }: WorkspaceDirPickerProps) {
  const t = useTranslations('chat.workspaceDir');
  const tIssue = useTranslations('common.workspacePathIssue');
  const chatId = useChatStore((s) => s.chatId);
  const actionMode = useChatStore((s) => s.actionMode);
  const workspaceDir = useChatStore((s) => s.workspaceDir);
  const [open, setOpen] = useState(false);
  const [currentDir, setCurrentDir] = useState<string | null>(null);
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [currentPath, setCurrentPath] = useState<string>('');
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [scaffolding, setScaffolding] = useState(false);
  const [pathInput, setPathInput] = useState('');
  const [filterQuery, setFilterQuery] = useState('');
  const loadGenRef = useRef(0);

  useEffect(() => {
    setCurrentDir(workspaceDir);
  }, [workspaceDir]);

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
    if (open) {
      loadDirectory(currentDir || '~');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only reload when popover opens
  }, [open]);

  const filteredEntries = useMemo(() => {
    if (!filterQuery.trim()) {
      return entries;
    }
    const q = filterQuery.toLowerCase();
    return entries.filter((e) => e.name.toLowerCase().includes(q));
  }, [entries, filterQuery]);

  // Read when the popover opens: the row is on every empty chat, and storage is only needed once it is used.
  const recentDirs = useMemo(() => (open ? getRecentDirectoryPaths(WORKSPACE_PICKER_RECENT_KEY) : []), [open]);

  const applyDir = async (dir: string | null) => {
    const previous = useChatStore.getState().workspaceDir;
    // Optimistic: the folder also takes effect when the chat row does not exist yet.
    useChatStore.getState().setWorkspaceDir(dir);
    setCurrentDir(dir);
    if (!chatId) {
      if (dir) {
        rememberDir(dir);
      }
      setOpen(false);
      return;
    }
    try {
      const result = await updateChatWorkspaceDir(chatId, dir);
      setCurrentDir(result.workspace_dir);
      useChatStore.getState().setWorkspaceDir(result.workspace_dir);
      if (result.workspace_dir) {
        rememberDir(result.workspace_dir);
      }
      toast({ title: dir ? t('updated') : t('cleared') });
      setOpen(false);
    } catch (error) {
      // 404: the chat row is written together with the first message, which carries the folder.
      if (error instanceof ApiError && error.code === 404) {
        if (dir) {
          rememberDir(dir);
        }
        setOpen(false);
        return;
      }
      const issueKey = workspacePathIssueMessageKey(error);
      useChatStore.getState().setWorkspaceDir(previous);
      setCurrentDir(previous);
      toast({ title: issueKey ? tIssue(issueKey) : t('invalidPath'), variant: 'destructive' });
    }
  };

  const handlePathInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && pathInput.trim()) {
      e.preventDefault();
      loadDirectory(pathInput.trim());
    }
  };

  const handleTauriNativePicker = async () => {
    try {
      const selected = await desktopBridge.openDirectoryPicker({
        title: t('selectThis'),
        defaultPath: currentDir || undefined,
      });
      if (selected) {
        const dir = typeof selected === 'string' ? selected : selected[0];
        await applyDir(dir);
      }
    } catch {
      // The native dialog is unavailable: fall back to the in-page picker, whose open effect loads the folder.
      setOpen(true);
    }
  };

  const handleScaffold = async () => {
    if (!currentDir || scaffolding) {
      return;
    }
    setScaffolding(true);
    try {
      const { entries: existing } = await browseDirectories(currentDir);
      const existingNames = new Set(existing.map((entry) => entry.name));
      const missing = OFFICE_FOLDERS.filter((folder) => !existingNames.has(folder));
      const results = await Promise.allSettled(missing.map((folder) => mkdirInWorkspace(currentDir, folder)));
      if (results.some((result) => result.status === 'rejected')) {
        toast({ title: t('scaffoldFailed'), variant: 'destructive' });
      } else {
        toast({ title: t('scaffoldDone') });
      }
    } catch {
      toast({ title: t('scaffoldFailed'), variant: 'destructive' });
    } finally {
      setScaffolding(false);
    }
  };

  if (actionMode !== 'agent') {
    return null;
  }

  const displayPath = currentDir ? compactPath(currentDir) : null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          title={currentDir ? t('tooltip') : t('sessionDefaultHint')}
          data-testid="workspace-dir-trigger"
          onClick={(e) => {
            if (desktopBridge.isDesktop()) {
              e.preventDefault();
              void handleTauriNativePicker();
            }
          }}
          className={cn(
            'group mt-2 flex min-w-0 items-center gap-2 rounded-xl border px-3 py-1.5 text-left text-xs transition-colors',
            currentDir
              ? 'w-fit max-w-full border-primary/25 bg-primary/5 text-foreground hover:bg-primary/10'
              : 'w-full border-dashed border-border bg-muted/40 text-muted-foreground hover:bg-muted/60 hover:text-foreground',
            className,
          )}
        >
          <FolderOpen className={cn('h-3.5 w-3.5 shrink-0', currentDir ? 'text-primary' : 'text-muted-foreground')} />
          <span className="min-w-0 flex-1 truncate font-medium">{displayPath ?? t('sessionDefault')}</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50 transition-transform group-data-[state=open]:rotate-180" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5 border-b border-border/60 px-2 py-1.5">
            {parentPath && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 rounded-lg"
                onClick={() => loadDirectory(parentPath)}
                title={t('back')}
              >
                <ArrowLeft className="h-3.5 w-3.5" />
              </Button>
            )}
            <Input
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              onKeyDown={handlePathInputKeyDown}
              className="h-6 flex-1 border-none bg-transparent px-1 text-xs shadow-none"
              placeholder={t('placeholder')}
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0 rounded-lg text-primary"
              onClick={() => applyDir(currentPath)}
              title={t('selectThis')}
            >
              <Check className="h-3.5 w-3.5" />
            </Button>
            {currentDir && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 rounded-lg text-destructive-text"
                onClick={() => applyDir(null)}
                title={t('clear')}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>

          {recentDirs.length > 0 && !loading && (
            <div className="border-b border-border/60 px-2 py-1.5">
              <div className="mb-1 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                <Clock className="h-2.5 w-2.5" />
                {t('recent')}
              </div>
              {recentDirs.map((dir) => (
                <button
                  key={dir}
                  type="button"
                  className="flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-xs transition-colors hover:bg-accent/50"
                  onClick={() => applyDir(dir)}
                >
                  <FolderOpen className="h-3 w-3 shrink-0 text-primary/60" />
                  <span className="truncate">{compactPath(dir)}</span>
                </button>
              ))}
            </div>
          )}

          {entries.length > 8 && !loading && (
            <div className="border-b border-border/60 px-2 py-1">
              <Input
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                className="h-6 border-none bg-muted/30 px-2 text-xs shadow-none"
                placeholder={t('filter')}
              />
            </div>
          )}

          <div className="max-h-52 overflow-y-auto p-1">
            {loading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : filteredEntries.length === 0 ? (
              <div className="py-6 text-center text-xs text-muted-foreground">{t('noSubdirs')}</div>
            ) : (
              filteredEntries.map((entry) => (
                <button
                  key={entry.path}
                  type="button"
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent/50"
                  onClick={() => loadDirectory(entry.path)}
                >
                  <FolderClosed className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="truncate">{entry.name}</span>
                  <ChevronRight className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                </button>
              ))
            )}
          </div>

          {currentDir && (
            <div className="border-t border-border/60 p-1.5">
              <button
                type="button"
                onClick={handleScaffold}
                disabled={scaffolding}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-60"
              >
                {scaffolding ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                ) : (
                  <FolderPlus className="h-3.5 w-3.5 shrink-0" />
                )}
                <span className="truncate">{t('scaffoldOffice')}</span>
              </button>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
