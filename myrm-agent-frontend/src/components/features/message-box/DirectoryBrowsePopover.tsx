'use client';

/**
 * [INPUT]
 * - @/services/chat::browseDirectories (POS: server directory browse API)
 *
 * [OUTPUT]
 * - DirectoryBrowsePopover: Web/local folder picker popover for directory grant flows
 *
 * [POS]
 * Reusable browse tree UI for HITL directory selection on non-Tauri surfaces.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowLeft, Check, ChevronRight, Clock, FolderClosed, FolderOpen } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { browseDirectories, type DirectoryEntry } from '@/services/chat';
import {
  DIRECTORY_GRANT_RECENT_KEY,
  getRecentDirectoryPaths,
  rememberDirectoryPath,
  shortenHomePath,
} from '@/lib/directoryBrowseRecent';
import { toast } from 'sonner';

export function rememberDirectoryGrantPath(dir: string): void {
  rememberDirectoryPath(DIRECTORY_GRANT_RECENT_KEY, dir);
}

export interface DirectoryBrowsePopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seedPath?: string;
  onSelect: (path: string) => void;
  trigger: React.ReactNode;
  disabled?: boolean;
}

export default function DirectoryBrowsePopover({
  open,
  onOpenChange,
  seedPath = '',
  onSelect,
  trigger,
  disabled = false,
}: DirectoryBrowsePopoverProps) {
  const t = useTranslations('chat.directoryRequest');
  const [currentPath, setCurrentPath] = useState(seedPath);
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pathInput, setPathInput] = useState(seedPath);
  const [filterQuery, setFilterQuery] = useState('');
  const loadGenRef = useRef(0);

  useEffect(() => {
    if (open) {
      setCurrentPath(seedPath);
      setPathInput(seedPath);
    }
  }, [open, seedPath]);

  const loadDirectory = useCallback(
    async (path: string) => {
      const gen = ++loadGenRef.current;
      setLoading(true);
      setFilterQuery('');
      try {
        const result = await browseDirectories(path);
        if (gen !== loadGenRef.current) return;
        setEntries(result.entries);
        setCurrentPath(result.current);
        setParentPath(result.parent);
        setPathInput(result.current);
      } catch {
        if (gen !== loadGenRef.current) return;
        toast.error(t('browseFailed'));
      } finally {
        if (gen === loadGenRef.current) setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (open) {
      void loadDirectory(seedPath.trim() || '~');
    }
  }, [open, seedPath, loadDirectory]);

  const filteredEntries = useMemo(() => {
    if (!filterQuery.trim()) return entries;
    const q = filterQuery.toLowerCase();
    return entries.filter((entry) => entry.name.toLowerCase().includes(q));
  }, [entries, filterQuery]);

  const handleSelect = useCallback(
    (dir: string) => {
      rememberDirectoryGrantPath(dir);
      onSelect(dir);
      onOpenChange(false);
    },
    [onOpenChange, onSelect],
  );

  const recentDirs = getRecentDirectoryPaths(DIRECTORY_GRANT_RECENT_KEY);

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild disabled={disabled}>
        {trigger}
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5 border-b px-2 py-1.5">
            {parentPath ? (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={() => void loadDirectory(parentPath)}
              >
                <ArrowLeft className="h-3.5 w-3.5" />
              </Button>
            ) : null}
            <Input
              value={pathInput}
              onChange={(event) => setPathInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && pathInput.trim()) {
                  event.preventDefault();
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
              disabled={!currentPath}
              onClick={() => currentPath && handleSelect(currentPath)}
              title={t('selectThis')}
            >
              <Check className="h-3.5 w-3.5" />
            </Button>
          </div>

          {recentDirs.length > 0 && !loading ? (
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
                  onClick={() => handleSelect(dir)}
                >
                  <FolderOpen className="h-3 w-3 shrink-0 text-primary/60" />
                  <span className="truncate">{shortenHomePath(dir)}</span>
                </button>
              ))}
            </div>
          ) : null}

          {entries.length > 8 && !loading ? (
            <div className="border-b px-2 py-1">
              <Input
                value={filterQuery}
                onChange={(event) => setFilterQuery(event.target.value)}
                className="h-6 border-none bg-muted/30 px-2 text-xs shadow-none focus-visible:ring-0"
                placeholder={t('filter')}
              />
            </div>
          ) : null}

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
  );
}
