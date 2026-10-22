'use client';

/**
 * [OUTPUT]
 * TurnLoadedSkillsButton: Sheet listing skills referenced during this assistant turn.
 *
 * [POS]
 * Chat message provenance action (metadata-only; no prompt impact).
 */

import { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/primitives/badge';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/primitives/sheet';
import { cn } from '@/lib/utils/classnameUtils';
import { IconWorkflow } from '@/components/features/icons/PremiumIcons';
import type { TurnLoadedSkillReceipt } from '@/store/chat/types';

interface TurnLoadedSkillsButtonProps {
  skills?: TurnLoadedSkillReceipt[];
}

const shortHash = (hash: string): string =>
  hash.length > 12 ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : hash;

export default function TurnLoadedSkillsButton({ skills }: TurnLoadedSkillsButtonProps) {
  const t = useTranslations('chat.turnLoadedSkills');
  const [open, setOpen] = useState(false);
  const rows = useMemo(() => skills ?? [], [skills]);

  if (rows.length === 0) {
    return null;
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl',
            'text-xs font-medium text-muted-foreground',
            'hover:bg-light-secondary dark:hover:bg-dark-secondary',
            'transition-colors active:scale-95',
          )}
          aria-label={t('triggerAria', { count: rows.length })}
        >
          <IconWorkflow className="w-3.5 h-3.5 opacity-80" />
          <span>{t('triggerLabel', { count: rows.length })}</span>
        </button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{t('title')}</SheetTitle>
          <SheetDescription>{t('description')}</SheetDescription>
        </SheetHeader>
        <ul className="mt-6 space-y-3">
          {rows.map((row) => (
            <li
              key={`${row.id}-${row.name}`}
              className="rounded-lg border border-border/60 bg-card/40 p-3 space-y-1.5"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium text-sm text-foreground break-all">{row.name}</span>
                {row.partial ? (
                  <Badge variant="secondary" className="shrink-0 text-[10px]">
                    {t('partialBadge')}
                  </Badge>
                ) : null}
              </div>
              {row.version ? (
                <p className="text-xs text-muted-foreground">
                  {t('versionLabel')}: {row.version}
                </p>
              ) : null}
              {row.content_hash ? (
                <p className="text-[11px] font-mono text-muted-foreground/80 break-all">
                  {t('hashLabel')}: {shortHash(row.content_hash)}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </SheetContent>
    </Sheet>
  );
}
