'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';
import { resolveCompanionBubbleTone, useCompanionThemeEpoch } from '@/services/companion/companionTheme';

import { pickPetBubbleSpec, type PetBubbleSpec } from './petStatusBubbleSpec';
import { PetState } from './PetStateMachine';

interface PetStatusBubbleProps {
  petState: PetState;
  className?: string;
}

export default function PetStatusBubble({ petState, className }: PetStatusBubbleProps) {
  const t = useTranslations('companion.sprite.bubble');
  const themeEpoch = useCompanionThemeEpoch();
  const [spec, setSpec] = useState<PetBubbleSpec | null>(null);
  const prevKeyRef = useRef<string | null>(null);

  useEffect(() => {
    const next = pickPetBubbleSpec(petState, prevKeyRef.current);
    if (next) {
      prevKeyRef.current = next.messageKey;
    }
    setSpec(next);
  }, [petState]);

  const toneVisual = useMemo(() => {
    if (!spec) {
      return resolveCompanionBubbleTone('neutral');
    }
    if (spec.tone === 'wait') {
      return resolveCompanionBubbleTone('wait');
    }
    if (spec.tone === 'error') {
      return resolveCompanionBubbleTone('error');
    }
    return resolveCompanionBubbleTone('neutral');
  }, [spec, themeEpoch]);

  if (!spec) {
    return null;
  }

  return (
    <div
      className={cn(
        'pointer-events-none absolute bottom-full left-1/2 mb-1 -translate-x-1/2',
        'max-w-[140px] rounded-md border bg-popover/95 px-2 py-1 text-center text-[11px] leading-tight shadow-md backdrop-blur-sm',
        className,
      )}
      style={{
        borderColor: toneVisual.borderColor,
        color: toneVisual.textColor,
      }}
    >
      {t(spec.messageKey)}
    </div>
  );
}
