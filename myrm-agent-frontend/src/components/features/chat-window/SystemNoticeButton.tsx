'use client';

/**
 * [INPUT]
 * - onOpenPlaybook: () => void
 * - ./MigrationDiscoveryBanner
 * - @/components/primitives/popover
 *
 * [OUTPUT]
 * - SystemNoticeButton: Compact notice and discovery popover for the empty-chat title row
 *
 * [POS]
 * Empty-chat secondary surface: keeps optional migration/update notices and the model-orchestration
 * playbook entry out of the first-screen stack while preserving one-click access.
 */

import React, { useState } from 'react';
import { Bell, BookOpen } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import MigrationDiscoveryBanner from './MigrationDiscoveryBanner';

interface SystemNoticeButtonProps {
  onOpenPlaybook: () => void;
}

export const SystemNoticeButton: React.FC<SystemNoticeButtonProps> = ({ onOpenPlaybook }) => {
  const t = useTranslations('chat.systemNotices');
  const [open, setOpen] = useState(false);

  const handleOpenPlaybook = () => {
    setOpen(false);
    onOpenPlaybook();
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={t('open')}
          className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-background/70 px-2.5 py-1 text-xs font-medium text-muted-foreground shadow-2xs backdrop-blur-xs transition-colors hover:border-border hover:text-foreground"
        >
          <Bell className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">{t('open')}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        side="bottom"
        className="max-h-[70vh] w-[min(92vw,420px)] overflow-y-auto p-3"
      >
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-foreground">
          <Bell className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          <span>{t('title')}</span>
        </div>
        <div className="space-y-2">
          <MigrationDiscoveryBanner />
        </div>
        <button
          type="button"
          onClick={handleOpenPlaybook}
          className="mt-3 flex w-full items-center gap-2 rounded-lg border border-border/60 bg-muted/30 px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted/60"
        >
          <BookOpen className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          <span>{t('playbook')}</span>
        </button>
      </PopoverContent>
    </Popover>
  );
};

export default SystemNoticeButton;
