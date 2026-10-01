'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Download } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import useChatStore from '@/store/useChatStore';
import { SessionExportModal } from './SessionExportModal';

interface SessionExportButtonProps {
  chatId: string;
  chatTitle?: string | null;
}

export default function SessionExportButton({ chatId, chatTitle }: SessionExportButtonProps) {
  const t = useTranslations('chat');
  const [modalOpen, setModalOpen] = useState(false);
  const storeTitle = useChatStore((s) => s.chatHistoryItems.find((c) => c.id === chatId)?.title);
  const resolvedTitle = chatTitle ?? storeTitle;

  useEffect(() => {
    const handleOpen = (e: Event) => {
      const customEvent = e as CustomEvent<{ chatId?: string }>;
      if (!customEvent.detail?.chatId || customEvent.detail.chatId === chatId) {
        setModalOpen(true);
      }
    };
    window.addEventListener('myrm:open-session-export', handleOpen);
    return () => window.removeEventListener('myrm:open-session-export', handleOpen);
  }, [chatId]);

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setModalOpen(true)}
        className="h-7 px-2 text-xs gap-1 border-border/50 hover:bg-muted/60 text-muted-foreground hover:text-foreground"
        title={t('exportChat.tooltip', { defaultMessage: '导出会话或复制 Markdown' })}
      >
        <Download className="h-3.5 w-3.5 text-primary" />
        <span>{t('exportChat.action', { defaultMessage: '导出' })}</span>
      </Button>

      <SessionExportModal open={modalOpen} onOpenChange={setModalOpen} chatId={chatId} chatTitle={resolvedTitle} />
    </>
  );
}
