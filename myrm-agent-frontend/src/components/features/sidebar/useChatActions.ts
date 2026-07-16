import { useCallback, useState } from 'react';
import { ChatItem, updateChatTitle, deleteChat, exportChat, createChatShare, revokeChatShare } from '@/services/chat';
import { copyAsMarkdown, downloadAsHtml, downloadAsJson, downloadAsMarkdown, printChat } from '@/lib/utils/chatExport';
import useChatStore from '@/store/useChatStore';
import { toast } from '@/hooks/useToast';
import type { useTranslations } from 'next-intl';

export function useChatActions(chatHistoryItems: ChatItem[], t: ReturnType<typeof useTranslations>) {
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [automationDialogOpen, setAutomationDialogOpen] = useState(false);
  const [automationChatId, setAutomationChatId] = useState<string | null>(null);
  const [automationChatTitle, setAutomationChatTitle] = useState<string | null>(null);
  const [handoffDialogOpen, setHandoffDialogOpen] = useState(false);
  const [handoffChatId, setHandoffChatId] = useState<string | null>(null);
  const [handoffChatTitle, setHandoffChatTitle] = useState('');
  const [handoffChatSource, setHandoffChatSource] = useState<string | undefined>(undefined);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [shareChatId, setShareChatId] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareExpiresAt, setShareExpiresAt] = useState<number | null>(null);
  const [shareLoading, setShareLoading] = useState(false);

  const { pinChat, unpinChat } = useChatStore();

  const handleRename = (chat: ChatItem) => {
    setRenameId(chat.id);
    setRenameValue(chat.title);
  };

  const handleRenameSubmit = async (chatId: string) => {
    try {
      await updateChatTitle(chatId, renameValue);
      const updatedItems = chatHistoryItems.map((chat) =>
        chat.id === chatId ? { ...chat, title: renameValue } : chat,
      );
      useChatStore.getState().setChatHistoryItems(updatedItems);
      setRenameId(null);
      setRenameValue('');
    } catch (error) {
      console.error('Failed to rename chat:', error);
      setRenameId(null);
      setRenameValue('');
    }
  };

  const handleRenameCancel = () => {
    setRenameId(null);
    setRenameValue('');
  };

  const handleDeleteClick = (chatId: string) => {
    setDeletingChatId(chatId);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!deletingChatId) return;

    const chatIdToDelete = deletingChatId;
    try {
      await deleteChat(chatIdToDelete);
      const removedChat = chatHistoryItems.find((chat) => chat.id === chatIdToDelete);
      const updatedItems = chatHistoryItems.filter((chat) => chat.id !== chatIdToDelete);
      useChatStore.getState().setChatHistoryItems(updatedItems);

      toast(t('chat.deleteChat.movedToTrash'), {
        description: t('chat.deleteChat.undoHint'),
        action: {
          label: t('chat.deleteChat.undo'),
          onClick: () => {
            import('@/services/chatTrash').then(({ restoreChat }) => {
              restoreChat(chatIdToDelete)
                .then(() => {
                  if (removedChat) {
                    useChatStore.getState().setChatHistoryItems([removedChat, ...updatedItems]);
                  }
                })
                .catch(() => {
                  toast({ title: t('chat.deleteChat.undoFailed'), variant: 'destructive' });
                });
            });
          },
        },
      });
    } catch (error) {
      console.error('Failed to delete chat:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      toast({
        title: t('chat.deleteChat.error'),
        description: errorMessage,
        variant: 'destructive',
      });
      throw error;
    } finally {
      setDeletingChatId(null);
    }
  };

  const handleExport = useCallback(
    async (chatId: string, mode: 'markdown' | 'json' | 'copy' | 'html' | 'print') => {
      setExportingId(chatId);
      try {
        const data = await exportChat(chatId);
        if (data.messages.length === 0) {
          toast({ title: t('chat.exportChat.noMessages'), variant: 'default' });
          return;
        }
        switch (mode) {
          case 'markdown':
            downloadAsMarkdown(data);
            toast({ title: t('chat.exportChat.success'), variant: 'default' });
            break;
          case 'json':
            downloadAsJson(data);
            toast({ title: t('chat.exportChat.success'), variant: 'default' });
            break;
          case 'html': {
            const isDark = document.documentElement.classList.contains('dark');
            const htmlLang = navigator.language.startsWith('zh') ? 'zh' : 'en';
            await downloadAsHtml(data, isDark ? 'dark' : 'light', htmlLang as 'en' | 'zh');
            toast({ title: t('chat.exportChat.success'), variant: 'default' });
            break;
          }
          case 'print': {
            const printDark = document.documentElement.classList.contains('dark');
            const printLang = navigator.language.startsWith('zh') ? 'zh' : 'en';
            await printChat(data, printDark ? 'dark' : 'light', printLang as 'en' | 'zh');
            break;
          }
          case 'copy':
            await copyAsMarkdown(data);
            toast({ title: t('chat.exportChat.copySuccess'), variant: 'default' });
            break;
        }
      } catch (error) {
        console.error('Export chat failed:', error);
        toast({
          title: t('chat.exportChat.error'),
          description: error instanceof Error ? error.message : 'Unknown error',
          variant: 'destructive',
        });
      } finally {
        setExportingId(null);
      }
    },
    [t],
  );

  const handlePin = useCallback(
    async (chatId: string) => {
      try {
        await pinChat(chatId);
      } catch (e) {
        toast({
          title: t('chat.pin.error'),
          description: e instanceof Error ? e.message : 'Unknown error',
          variant: 'destructive',
        });
      }
    },
    [pinChat, t],
  );

  const handleUnpin = useCallback(
    async (chatId: string) => {
      try {
        await unpinChat(chatId);
      } catch (e) {
        toast({
          title: t('chat.unpin.error'),
          description: e instanceof Error ? e.message : 'Unknown error',
          variant: 'destructive',
        });
      }
    },
    [unpinChat, t],
  );

  const handleCreateAutomation = useCallback((chatId: string, chatTitle: string) => {
    setAutomationChatId(chatId);
    setAutomationChatTitle(chatTitle);
    setAutomationDialogOpen(true);
  }, []);

  const handleHandoff = useCallback((chatId: string, chatTitle: string, source?: string) => {
    setHandoffChatId(chatId);
    setHandoffChatTitle(chatTitle);
    setHandoffChatSource(source);
    setHandoffDialogOpen(true);
  }, []);

  const handleShare = useCallback((chatId: string) => {
    setShareChatId(chatId);
    setShareUrl(null);
    setShareExpiresAt(null);
    setShareDialogOpen(true);
  }, []);

  const handleShareCreate = useCallback(
    async (ttlDays: number = 7) => {
      if (!shareChatId) return;
      setShareLoading(true);
      try {
        const result = await createChatShare(shareChatId, ttlDays);
        setShareUrl(result.share_url);
        setShareExpiresAt(result.expires_at);
      } catch (error) {
        toast({
          title: t('chat.share.error'),
          description: error instanceof Error ? error.message : 'Unknown error',
          variant: 'destructive',
        });
      } finally {
        setShareLoading(false);
      }
    },
    [shareChatId, t],
  );

  const handleShareRevoke = useCallback(async () => {
    if (!shareChatId) return;
    try {
      await revokeChatShare(shareChatId);
      setShareUrl(null);
      setShareExpiresAt(null);
      toast({ title: t('chat.share.revoked'), variant: 'default' });
      setShareDialogOpen(false);
    } catch (error) {
      toast({
        title: t('chat.share.error'),
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  }, [shareChatId, t]);

  return {
    renameId,
    renameValue,
    setRenameValue,
    deleteDialogOpen,
    setDeleteDialogOpen,
    exportingId,
    automationDialogOpen,
    setAutomationDialogOpen,
    automationChatId,
    automationChatTitle,
    handoffDialogOpen,
    setHandoffDialogOpen,
    handoffChatId,
    handoffChatTitle,
    handoffChatSource,
    handleRename,
    handleRenameSubmit,
    handleRenameCancel,
    handleDeleteClick,
    handleDeleteConfirm,
    handleExport,
    handlePin,
    handleUnpin,
    handleCreateAutomation,
    handleHandoff,
    handleShare,
    handleShareCreate,
    handleShareRevoke,
    shareDialogOpen,
    setShareDialogOpen,
    shareChatId,
    shareUrl,
    shareExpiresAt,
    shareLoading,
  };
}
