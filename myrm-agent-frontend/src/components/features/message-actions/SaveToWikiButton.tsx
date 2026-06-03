'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { BookPlus, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { wikiService } from '@/services/wikiService';
import type { Message } from '@/store/chat/types';
import {
  filterFolderNodes,
  getWikiOperationErrorMessage,
  isNotFoundApiError,
} from '@/components/features/settings/sections/wiki/wikiTreeUtils';
import { WikiFolderSelectTree } from '@/components/features/settings/sections/wiki/WikiFolderSelectTree';

interface SaveToWikiButtonProps {
  message: Message;
}

function buildWikiContentWithProvenance(message: Message): string {
  const savedAt = new Date().toISOString();
  const frontmatter = [
    '---',
    `source_chat: ${message.chatId}`,
    `source_message: ${message.messageId}`,
    `saved_at: ${savedAt}`,
    '---',
    '',
  ].join('\n');
  return `${frontmatter}${message.content}`;
}

export default function SaveToWikiButton({ message }: SaveToWikiButtonProps) {
  const t = useTranslations('settings.wiki.saveToWiki');
  const [isOpen, setIsOpen] = useState(false);
  const [treeData, setTreeData] = useState<ReturnType<typeof filterFolderNodes>>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [filename, setFilename] = useState('');
  const [overwritePath, setOverwritePath] = useState<string | null>(null);

  const fetchTree = async () => {
    try {
      setIsLoading(true);
      const res = await wikiService.getTree();
      setTreeData(filterFolderNodes(res));
    } catch (error) {
      console.error('Failed to load wiki tree:', error);
      toast.error(t('loadFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;

    void fetchTree();
    const snippet = message.content
      .substring(0, 20)
      .replace(/[^\w\s]/gi, '')
      .trim()
      .replace(/\s+/g, '-')
      .toLowerCase();
    setFilename(snippet || 'untitled-note');
    setOverwritePath(null);
  }, [isOpen, message.content]);

  const buildFullPath = () => (selectedFolder ? `${selectedFolder}/${filename}` : filename);

  const performSave = async (fullPath: string) => {
    setIsSaving(true);
    try {
      await wikiService.updateConcept(fullPath, buildWikiContentWithProvenance(message));
      toast.success(t('saveSuccess'));
      setIsOpen(false);
      setOverwritePath(null);
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('saveFailed')));
    } finally {
      setIsSaving(false);
    }
  };

  const handleSave = async () => {
    if (!filename) {
      toast.error(t('filenameRequired'));
      return;
    }

    const fullPath = buildFullPath();
    try {
      await wikiService.getConcept(fullPath);
      setOverwritePath(fullPath);
    } catch (error) {
      if (isNotFoundApiError(error)) {
        await performSave(fullPath);
      } else {
        toast.error(getWikiOperationErrorMessage(error, t('saveFailed')));
      }
    }
  };

  const selectedPath = buildFullPath();

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="p-2 text-black/70 dark:text-white/70 hover:bg-light-secondary dark:hover:bg-dark-secondary rounded-xl transition duration-200 hover:text-black dark:hover:text-white active:scale-95"
        title={t('buttonTitle')}
        aria-label={t('buttonTitle')}
      >
        <BookPlus className="w-4 h-4" />
      </button>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>{t('title')}</DialogTitle>
            <DialogDescription>{t('description')}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">{t('filenameLabel')}</label>
              <Input
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                placeholder={t('filenamePlaceholder')}
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">{t('folderLabel')}</label>
              <div className="border rounded-md h-[200px] overflow-auto p-2 bg-muted/20">
                {isLoading ? (
                  <div className="flex justify-center items-center h-full">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                  </div>
                ) : treeData.length === 0 ? (
                  <div className="text-center text-sm text-muted-foreground mt-8">{t('noFolders')}</div>
                ) : (
                  <WikiFolderSelectTree
                    data={treeData}
                    height={180}
                    selectedFolder={selectedFolder}
                    onSelectFolder={setSelectedFolder}
                  />
                )}
              </div>
              <div className="text-xs text-muted-foreground">
                {t('selectedPath')} <span className="font-mono">{selectedPath}</span>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsOpen(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={() => void handleSave()} disabled={isSaving || !filename}>
              {isSaving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={overwritePath !== null} onOpenChange={(open) => !open && setOverwritePath(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('overwriteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('overwriteDescription', { path: overwritePath ?? '' })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (overwritePath) void performSave(overwritePath);
              }}
            >
              {t('overwriteConfirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
