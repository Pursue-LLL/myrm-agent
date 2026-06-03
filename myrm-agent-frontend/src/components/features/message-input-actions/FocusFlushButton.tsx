import * as React from 'react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import { toast } from 'sonner';
import { focusFlushChat } from '@/services/chat';
import { AiMagicIcon } from 'hugeicons-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/primitives/alert-dialog';

const FocusFlushButton = () => {
  const commonT = useTranslations('common');
  const { chatId, resetSessionState, loadMessages, stopMessage } = useChatStore(
    useShallow((state) => ({
      chatId: state.chatId,
      resetSessionState: state.resetSessionState,
      loadMessages: state.loadMessages,
      stopMessage: state.stopMessage,
    })),
  );

  const [isOpen, setIsOpen] = React.useState(false);

  const handleFocus = async () => {
    if (!chatId) return;

    setIsOpen(false); // Close dialog immediately
    const toastId = toast.loading('Flushing chat history...');
    try {
      // Force kill any active backend agent request for this chat to prevent state tearing
      stopMessage();

      const result = await focusFlushChat(chatId);
      if (result.cleared) {
        toast.success('Chat history cleared. Sandbox environment retained.', { id: toastId });
        resetSessionState();
        await loadMessages(chatId);
      }
    } catch {
      toast.error('Failed to flush chat', { id: toastId });
    }
  };

  if (!chatId) return null;

  return (
    <AlertDialog open={isOpen} onOpenChange={setIsOpen}>
      <AlertDialogTrigger asChild>
        <button
          type="button"
          className="flex items-center justify-center p-1.5 md:p-2 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-full transition-colors"
          title="Focus mode (Clear chat history but keep Sandbox)"
          aria-label="Focus mode"
        >
          <AiMagicIcon size={18} />
        </button>
      </AlertDialogTrigger>
      <AlertDialogContent className="sm:max-w-[425px]">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AiMagicIcon size={22} className="text-primary" />
            Focus Session (Clear History)
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base pt-2 text-muted-foreground">
            Are you sure you want to clear this conversation's history? <br />
            <br />
            This will give the Agent a fresh context and{' '}
            <strong className="text-foreground font-medium">save Token costs</strong>, but your{' '}
            <strong className="text-foreground font-medium">
              Sandbox environment, files, and installed packages will remain intact
            </strong>
            .
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="border-border hover:bg-muted/50">{commonT('cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={handleFocus} className="bg-primary text-primary-foreground hover:bg-primary/90">
            Clear History
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default FocusFlushButton;
