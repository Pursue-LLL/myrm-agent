'use client';

import { Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/useToast';
import { ChatItem, deleteChat as deleteChatService } from '@/services/chat';
import { restoreChat } from '@/services/chatTrash';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';

const DeleteChat = ({
  chatId,
  chats,
  setChats,
  redirect = false,
  onTrashCountChange,
}: {
  chatId: string;
  chats: ChatItem[];
  setChats: (chats: ChatItem[]) => void;
  redirect?: boolean;
  onTrashCountChange?: () => void;
}) => {
  const t = useTranslations('chat.deleteChat');

  const handleDelete = async () => {
    try {
      await deleteChatService(chatId);

      const removedChat = chats.find((chat) => chat.id === chatId);
      const newChats = chats.filter((chat) => chat.id !== chatId);
      setChats(newChats);
      onTrashCountChange?.();

      toast(t('movedToTrash'), {
        description: t('undoHint'),
        action: {
          label: t('undo'),
          onClick: () => {
            restoreChat(chatId)
              .then(() => {
                if (removedChat) {
                  setChats([removedChat, ...newChats]);
                }
                onTrashCountChange?.();
              })
              .catch(() => {
                toast({ title: t('undoFailed'), variant: 'destructive' });
              });
          },
        },
      });

      if (redirect) {
        window.location.href = '/';
      }
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      toast({
        title: t('error'),
        description: errorMessage,
        variant: 'destructive',
      });
      throw err;
    }
  };

  return (
    <ConfirmDialog
      trigger={
        <button
          className="group bg-transparent text-red-400 hover:text-red-500 hover:scale-110 active:scale-95 transition-all duration-200 hover:rotate-6"
          aria-label={t('title')}
        >
          <Trash2
            size={17}
            className="group-hover:drop-shadow-[0_2px_8px_rgba(239,68,68,0.5)] transition-all duration-300"
          />
        </button>
      }
      title={t('title')}
      description={t('description')}
      confirmText={t('confirm')}
      cancelText={t('cancel')}
      loadingText={t('deleting')}
      variant="destructive"
      onConfirm={handleDelete}
    />
  );
};

export default DeleteChat;
