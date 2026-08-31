'use client';

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { FolderOpen, FolderClosed, ChevronRight, ArrowLeft, X, Check, Clock } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { browseDirectories, updateChatWorkspaceDir, type DirectoryEntry } from '@/services/chat';
import { toast } from '@/hooks/shared/useToast';
import useChatStore from '@/store/useChatStore';
import { desktopBridge } from '@/lib/desktopBridge';

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

interface WorkspaceDirPickerProps {
  className?: string;
}

export default function WorkspaceDirPicker({ className }: WorkspaceDirPickerProps) {
  const t = useTranslations('chat.workspaceDir');
  const chatId = useChatStore((s) => s.chatId);
  const actionMode = useChatStore((s) => s.actionMode);
  const workspaceDir = useChatStore((s) => s.workspaceDir);
  const [open, setOpen] = useState(false);
  const [currentDir, setCurrentDir] = useState<string | null>(null);
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [currentPath, setCurrentPath] = useState<string>('');
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
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

  if (actionMode !== 'agent') {
    return null;
  }

  const applyDir = async (dir: string | null) => {
    if (!chatId) {
      return;
    }
    try {
      const result = await updateChatWorkspaceDir(chatId, dir);
      setCurrentDir(result.workspace_dir);
      useChatStore.getState().setWorkspaceDir(result.workspace_dir);
      if (result.workspace_dir) {
        addRecentDir(result.workspace_dir);
      }
      toast({ title: dir ? t('updated') : t('cleared') });
      setOpen(false);
    } catch {
      toast({ title: t('invalidPath'), variant: 'destructive' });
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
      loadDirectory(currentDir || '~');
    }
  };

  const shortenHome = (p: string) => p.replace(/^\/(?:Users|home)\/[^/]+/, '~');

  const displayPath = currentDir ? shortenHome(currentDir) : null;
  const recentDirs = getRecentDirs();

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn(
            'h-7 shrink-0 gap-1.5 text-xs font-normal whitespace-nowrap text-muted-foreground hover:text-foreground',
            currentDir && 'text-primary/80',
            className,
          )}
          title={t('tooltip')}
          onClick={(e) => {
            if (desktopBridge.isDesktop()) {
              e.preventDefault();
              handleTauriNativePicker();
            }
          }}
        >
          <FolderOpen className={cn('h-3.5 w-3.5', !currentDir && 'text-amber-500/80')} />
          {displayPath ? (
            <span className="max-w-[120px] truncate">{displayPath}</span>
          ) : (
            <span className="hidden xl:inline text-amber-500/90 font-medium">{t('unboundWarning') || t('label')}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="flex flex-col">
          {/* Path input header */}
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
              onKeyDown={handlePathInputKeyDown}
              className="h-6 flex-1 border-none bg-transparent px-1 text-xs shadow-none focus-visible:ring-0"
              placeholder={t('placeholder')}
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0 text-primary"
              onClick={() => applyDir(currentPath)}
              title={t('selectThis')}
            >
              <Check className="h-3.5 w-3.5" />
            </Button>
            {currentDir && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 text-destructive"
                onClick={() => applyDir(null)}
                title={t('clear')}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>

          {/* Recent directories */}
          {recentDirs.length > 0 && !loading && (
            <div className="border-b px-2 py-1.5">
              <div className="mb-1 flex items-center gap-1 text-[10px] font-medium uppercase text-muted-foreground">
                <Clock className="h-2.5 w-2.5" />
                {t('recent')}
              </div>
              {recentDirs.map((dir) => (
                <button
                  key={dir}
                  className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs hover:bg-accent/50 transition-colors"
                  onClick={() => applyDir(dir)}
                >
                  <FolderOpen className="h-3 w-3 shrink-0 text-primary/60" />
                  <span className="truncate">{shortenHome(dir)}</span>
                </button>
              ))}
            </div>
          )}

          {/* Filter input (shown when entries > 8) */}
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

          {/* Directory list */}
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
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent/50 transition-colors"
                  onClick={() => loadDirectory(entry.path)}
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
  );
}
