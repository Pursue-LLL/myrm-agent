'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';

import { pickPetBubbleSpec, type PetBubbleSpec } from './petStatusBubbleSpec';
import { PetState } from './PetStateMachine';

interface PetStatusBubbleProps {
  petState: PetState;
  className?: string;
}

export default function PetStatusBubble({ petState, className }: PetStatusBubbleProps) {
  const t = useTranslations('companion.sprite.bubble');
  const [spec, setSpec] = useState<PetBubbleSpec | null>(null);
  const prevKeyRef = useRef<string | null>(null);

  useEffect(() => {
    const next = pickPetBubbleSpec(petState, prevKeyRef.current);
    if (next) {
      prevKeyRef.current = next.messageKey;
    }
    setSpec(next);
  }, [petState]);

  if (!spec) {
    return null;
  }

  const toneClass =
    spec.tone === 'wait'
      ? 'border-amber-500/40 text-amber-100'
      : spec.tone === 'error'
        ? 'border-red-500/40 text-red-100'
        : 'border-border/60 text-foreground';

  return (
    <div
      className={cn(
        'pointer-events-none absolute bottom-full left-1/2 mb-1 -translate-x-1/2',
        'max-w-[140px] rounded-md border bg-popover/95 px-2 py-1 text-center text-[11px] leading-tight shadow-md backdrop-blur-sm',
        toneClass,
        className,
      )}
    >
      {t(spec.messageKey)}
    </div>
  );
}
