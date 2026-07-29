'use client';

/**
 * [INPUT]
 * @/store/useChatStore::agentConfig (POS: Chat session agent scope)
 * @/services/wikiService::wikiService (POS: Wiki REST client with explicit agentId)
 *
 * [OUTPUT]
 * SaveToWikiButton: Save assistant message content into the active agent wiki vault.
 *
 * [POS]
 * Chat message action. Writes scoped concepts via the same agentId contract as ArtifactCard ingest.
 */

import { useState, useEffect, useCallback } from 'react';
import { useLocale, useTranslations } from 'next-intl';
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
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { wikiService } from '@/services/wikiService';
import useChatStore from '@/store/useChatStore';
import type { Message } from '@/store/chat/types';
import {
  filterFolderNodes,
  getWikiOperationErrorMessage,
  getWikiErrorCode,
  isNotFoundApiError,
} from '@/components/features/settings/sections/knowledge/wiki/wikiTreeUtils';
import { WikiFolderSelectTree } from '@/components/features/settings/sections/knowledge/wiki/WikiFolderSelectTree';

interface SaveToWikiButtonProps {
  message: Message;
}

function buildSaveMetadata(message: Message): Record<string, string> {
  return {
    source_chat: message.chatId,
    source_message: message.messageId,
    saved_at: new Date().toISOString(),
  };
}

export default function SaveToWikiButton({ message }: SaveToWikiButtonProps) {
  const t = useTranslations('settings.wiki.saveToWiki');
  const tWiki = useTranslations('settings.wiki');
  const locale = useLocale();
  const agentId = useChatStore((state) => state.agentConfig?.agentId);
  const agentName = useChatStore((state) => state.agentConfig?.agentName);
  const scopeLabel = agentId
    ? getBuiltinAgentName(agentId, agentName ?? agentId, locale)
    : tWiki('agentScopeDefault');
  const [isOpen, setIsOpen] = useState(false);
  const [treeData, setTreeData] = useState<ReturnType<typeof filterFolderNodes>>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [filename, setFilename] = useState('');
  const [overwritePath, setOverwritePath] = useState<string | null>(null);

  const fetchTree = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await wikiService.getTree(agentId);
      setTreeData(filterFolderNodes(res));
    } catch (error) {
      console.error('Failed to load wiki tree:', error);
      toast.error(t('loadFailed'));
    } finally {
      setIsLoading(false);
    }
  }, [agentId, t]);

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
    setSelectedFolder(null);
  }, [fetchTree, isOpen, message.content]);

  const buildFullPath = () => (selectedFolder ? `${selectedFolder}/${filename}` : filename);

  const performSave = async (fullPath: string, overwrite = false) => {
    setIsSaving(true);
    try {
      if (overwrite) {
        const savedAt = new Date().toISOString();
        await wikiService.applyWiki(
          {
            op: 'patch_compiled_truth',
            concept_name: fullPath,
            compiled_truth: message.content,
          },
          agentId,
          'chat',
        );
        await wikiService.applyWiki(
          {
            op: 'append_timeline',
            concept_name: fullPath,
            timeline_entry: `Updated from chat at ${savedAt}`,
          },
          agentId,
          'chat',
        );
      } else {
        await wikiService.applyWiki(
          {
            op: 'create_note',
            concept_name: fullPath,
            body: message.content,
            metadata: buildSaveMetadata(message),
            provenance: 'chat-save',
          },
          agentId,
          'chat',
        );
      }
      toast.success(t('saveSuccess'));
      setIsOpen(false);
      setOverwritePath(null);
    } catch (error) {
      const code = getWikiErrorCode(error);
      if (code === 'canonical_conflict') {
        toast.error(t('canonicalConflict'));
      } else {
        toast.error(getWikiOperationErrorMessage(error, t('saveFailed')));
      }
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
      await wikiService.getConcept(fullPath, agentId);
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
            <p className="text-xs text-muted-foreground">{tWiki('scopeChip.label', { scope: scopeLabel })}</p>
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
                if (overwritePath) void performSave(overwritePath, true);
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
