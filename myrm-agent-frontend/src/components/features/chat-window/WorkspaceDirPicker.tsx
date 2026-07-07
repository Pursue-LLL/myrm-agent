'use client';

import { useState, useCallback, useEffect } from 'react';
import { FolderOpen, FolderClosed, ChevronRight, ArrowLeft, X, Check } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { browseDirectories, updateChatWorkspaceDir, type DirectoryEntry } from '@/services/chat';
import { toast } from '@/hooks/useToast';
import useChatStore from '@/store/useChatStore';

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

  // Sync from store
  useEffect(() => {
    setCurrentDir(workspaceDir);
  }, [workspaceDir]);

  const loadDirectory = useCallback(
    async (path: string) => {
      setLoading(true);
      try {
        const result = await browseDirectories(path);
        setEntries(result.entries);
        setCurrentPath(result.current);
        setParentPath(result.parent);
      } catch {
        toast({ title: t('invalidPath'), variant: 'destructive' });
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (open) {
      loadDirectory(currentDir || '~');
    }
  }, [open, currentDir, loadDirectory]);

  // Only show in agent mode
  if (actionMode !== 'agent') return null;

  const handleSelect = async () => {
    if (!chatId) return;
    try {
      const result = await updateChatWorkspaceDir(chatId, currentPath);
      setCurrentDir(result.workspace_dir);
      useChatStore.getState().setWorkspaceDir(result.workspace_dir);
      toast({ title: t('updated') });
      setOpen(false);
    } catch {
      toast({ title: t('invalidPath'), variant: 'destructive' });
    }
  };

  const handleClear = async () => {
    if (!chatId) return;
    try {
      await updateChatWorkspaceDir(chatId, null);
      setCurrentDir(null);
      useChatStore.getState().setWorkspaceDir(null);
      toast({ title: t('cleared') });
      setOpen(false);
    } catch {
      toast({ title: t('invalidPath'), variant: 'destructive' });
    }
  };

  const shortenHome = (p: string) => p.replace(/^\/(?:Users|home)\/[^/]+/, '~');

  const displayPath = currentDir ? shortenHome(currentDir) : null;

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
        >
          <FolderOpen className="h-3.5 w-3.5" />
          {displayPath ? (
            <span className="max-w-[120px] truncate">{displayPath}</span>
          ) : (
            <span className="hidden xl:inline">{t('label')}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between border-b px-3 py-2">
            <div className="flex items-center gap-2">
              {parentPath && (
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => loadDirectory(parentPath)}>
                  <ArrowLeft className="h-3.5 w-3.5" />
                </Button>
              )}
              <span className="text-xs font-medium text-muted-foreground truncate max-w-[180px]">
                {shortenHome(currentPath)}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-primary"
                onClick={handleSelect}
                title={t('selectThis')}
              >
                <Check className="h-3.5 w-3.5" />
              </Button>
              {currentDir && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-destructive"
                  onClick={handleClear}
                  title={t('clear')}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          </div>

          {/* Directory list */}
          <div className="max-h-60 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-6">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              </div>
            ) : entries.length === 0 ? (
              <div className="py-6 text-center text-xs text-muted-foreground">{t('noSubdirs')}</div>
            ) : (
              entries.map((entry) => (
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
