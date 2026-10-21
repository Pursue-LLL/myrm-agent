'use client';

import { X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { formatSkillChipLabel } from '@/lib/utils/messageUtils';
import { useTranslations } from 'next-intl';

export interface SkillActivationChipsProps {
  skillNames: string[];
  instruction?: string | null;
  className?: string;
  onRemove?: () => void;
}

export function SkillActivationChips({ skillNames, instruction, className, onRemove }: SkillActivationChipsProps) {
  const t = useTranslations('chat.skillActivation');

  if (skillNames.length === 0) {
    return null;
  }

  return (
    <div data-testid="skill-activation-chips" className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {skillNames.map((name) => (
        <span
          key={name}
          className="inline-flex h-6 max-w-full items-center rounded-md border border-primary/20 bg-primary/10 px-2 text-xs font-medium leading-none text-primary shadow-xs"
          title={name}
        >
          <span className="truncate">{formatSkillChipLabel(name)}</span>
        </span>
      ))}
      {instruction ? (
        <span
          className="inline-flex h-6 max-w-full items-center rounded-md border border-border/60 bg-muted/60 px-2 text-xs text-muted-foreground"
          title={instruction}
        >
          <span className="truncate">{instruction}</span>
        </span>
      ) : null}
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-border/60 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label={t('remove')}
        >
          <X size={12} />
        </button>
      ) : null}
    </div>
  );
}
