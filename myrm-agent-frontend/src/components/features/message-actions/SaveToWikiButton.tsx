'use client';

/**
 * [INPUT]
 * @/store/useChatStore::agentConfig, messages (POS: Chat session agent scope + thread)
 * @/services/wikiService::compoundWiki (POS: Wiki REST client — ids only; server hydrates Q&A)
 *
 * [OUTPUT]
 * SaveToWikiButton: Stage assistant message Q&A into Wiki pending review (HITL).
 *
 * [POS]
 * Chat message action. Uses POST /wiki/compound — never direct publish.
 */

import { useState, useEffect, useCallback } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
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
} from '@/components/features/settings/sections/knowledge/wiki/wikiTreeUtils';
import { WikiFolderSelectTree } from '@/components/features/settings/sections/knowledge/wiki/WikiFolderSelectTree';

interface SaveToWikiButtonProps {
  message: Message;
  messageIndex: number;
}

function defaultCompoundFolder(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `ChatCompounds/${now.getFullYear()}-${month}`;
}

export default function SaveToWikiButton({ message, messageIndex: _messageIndex }: SaveToWikiButtonProps) {
  void _messageIndex;
  const t = useTranslations('settings.wiki.saveToWiki');
  const tWiki = useTranslations('settings.wiki');
  const locale = useLocale();
  const router = useRouter();
  const agentId = useChatStore((state) => state.agentConfig?.agentId);
  const agentName = useChatStore((state) => state.agentConfig?.agentName);
  const enabledBuiltinTools = useChatStore(
    (state) => state.agentConfig?.enabledBuiltinTools ?? state.currentBuiltinTools,
  );
  const incognitoMode = useChatStore((state) => state.incognitoMode);
  const wikiEnabled = enabledBuiltinTools.includes('wiki');
  const scopeLabel = agentId
    ? getBuiltinAgentName(agentId, agentName ?? agentId, locale)
    : tWiki('agentScopeDefault');
  const [isOpen, setIsOpen] = useState(false);
  const [treeData, setTreeData] = useState<ReturnType<typeof filterFolderNodes>>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [filename, setFilename] = useState('');

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
    setSelectedFolder(defaultCompoundFolder());
  }, [fetchTree, isOpen, message.content]);

  if (!wikiEnabled || incognitoMode || !message.content.trim() || !message.chatId || !message.messageId) {
    return null;
  }

  const buildFullPath = () => {
    const folder = selectedFolder?.trim();
    return folder ? `${folder}/${filename}` : filename;
  };

  const openPendingSettings = () => {
    const params = new URLSearchParams({ wikiTab: 'pendingEdits' });
    if (agentId) {
      params.set('agentId', agentId);
    }
    router.push(`/settings/wiki?${params.toString()}`);
  };

  const handleSave = async () => {
    if (!filename.trim()) {
      toast.error(t('filenameRequired'));
      return;
    }

    setIsSaving(true);
    try {
      await wikiService.compoundWiki(
        {
          concept_name: buildFullPath(),
          source_chat: message.chatId,
          source_message: message.messageId,
        },
        agentId,
      );
      toast.success(t('compoundSuccess'), {
        action: {
          label: t('openPending'),
          onClick: openPendingSettings,
        },
      });
      setIsOpen(false);
    } catch (error) {
      const code = getWikiErrorCode(error);
      if (code === 'already_staged') {
        toast.info(t('alreadyStaged'), {
          action: {
            label: t('openPending'),
            onClick: openPendingSettings,
          },
        });
        setIsOpen(false);
        return;
      }
      if (code === 'message_not_found') {
        toast.error(t('messageNotFound'));
        return;
      }
      if (code === 'incognito_forbidden') {
        toast.error(t('incognitoForbidden'));
        return;
      }
      toast.error(getWikiOperationErrorMessage(error, t('saveFailed')));
    } finally {
      setIsSaving(false);
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
    </>
  );
}
