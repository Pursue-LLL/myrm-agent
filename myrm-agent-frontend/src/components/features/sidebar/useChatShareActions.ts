import { useCallback, useState } from 'react';
import { createChatShare, revokeChatShare, getChatShareStatus } from '@/services/chat';
import { toast } from '@/hooks/shared/useToast';
import type { useTranslations } from 'next-intl';

export function useChatShareActions(t: ReturnType<typeof useTranslations>) {
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [shareChatId, setShareChatId] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareExpiresAt, setShareExpiresAt] = useState<number | null>(null);
  const [shareRevoked, setShareRevoked] = useState(false);
  const [sharePasswordProtected, setSharePasswordProtected] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);

  const handleShare = useCallback(async (chatId: string) => {
    setShareChatId(chatId);
    setShareUrl(null);
    setShareExpiresAt(null);
    setShareRevoked(false);
    setSharePasswordProtected(false);
    setShareDialogOpen(true);
    setShareLoading(true);
    try {
      const status = await getChatShareStatus(chatId);
      if (!status.shared) {
        return;
      }
      setShareRevoked(status.revoked);
      setSharePasswordProtected(status.password_protected);
      if (status.share_url) {
        setShareUrl(status.share_url);
      }
      if (status.expires_at) {
        setShareExpiresAt(status.expires_at);
      }
    } catch {
      // Query failure falls back to create form; dialog stays usable.
    } finally {
      setShareLoading(false);
    }
  }, []);

  const handleShareCreate = useCallback(
    async (ttlDays: number = 7, password?: string) => {
      if (!shareChatId) {
        return;
      }
      setShareLoading(true);
      try {
        const result = await createChatShare(shareChatId, ttlDays, password);
        setShareUrl(result.share_url);
        setShareExpiresAt(result.expires_at);
        setShareRevoked(false);
        setSharePasswordProtected(result.password_protected);
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
    if (!shareChatId) {
      return;
    }
    try {
      await revokeChatShare(shareChatId);
      setShareUrl(null);
      setShareExpiresAt(null);
      setSharePasswordProtected(false);
      setShareRevoked(true);
      toast({ title: t('chat.share.revoked'), variant: 'default' });
    } catch (error) {
      toast({
        title: t('chat.share.error'),
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  }, [shareChatId, t]);

  return {
    shareDialogOpen,
    setShareDialogOpen,
    shareChatId,
    shareUrl,
    shareExpiresAt,
    shareRevoked,
    sharePasswordProtected,
    shareLoading,
    handleShare,
    handleShareCreate,
    handleShareRevoke,
  };
}
