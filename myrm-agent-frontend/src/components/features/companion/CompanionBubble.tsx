'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';

import { getObserverLimits } from './companionGenerator';

import type { Rarity } from './companionGenerator';

type BubbleMode = 'thinking' | 'completion' | 'observer' | 'hidden';

const THINKING_COUNT = 26;
const COMPLETION_COUNT = 11;
const THINKING_ROTATE_MIN_MS = 3000;
const THINKING_ROTATE_MAX_MS = 5000;
const FADE_RATIO = 0.3;

interface CompanionBubbleProps {
  mode: BubbleMode;
  observerText?: string | null;
  effectiveRarity?: Rarity;
}

export default function CompanionBubble({ mode, observerText, effectiveRarity = 'Common' }: CompanionBubbleProps) {
  const t = useTranslations('companion');
  const [text, setText] = useState('');
  const [fading, setFading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { displayDurationMs } = getObserverLimits(effectiveRarity);
  const fadeDurationMs = Math.round(displayDurationMs * FADE_RATIO);

  const clearTimers = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
  }, []);

  const pickThinkingPhrase = useCallback(() => {
    const idx = Math.floor(Math.random() * THINKING_COUNT);
    return t(`thinking.${idx}`);
  }, [t]);

  const pickCompletionPhrase = useCallback(() => {
    const idx = Math.floor(Math.random() * COMPLETION_COUNT);
    return t(`completion.${idx}`);
  }, [t]);

  useEffect(() => {
    clearTimers();
    setFading(false);

    if (mode === 'hidden') {
      setText('');
      return;
    }

    if (mode === 'thinking') {
      setText(pickThinkingPhrase());
      const rotate = () => {
        const delay = THINKING_ROTATE_MIN_MS + Math.random() * (THINKING_ROTATE_MAX_MS - THINKING_ROTATE_MIN_MS);
        timerRef.current = setTimeout(() => {
          setText(pickThinkingPhrase());
          rotate();
        }, delay);
      };
      rotate();
      return () => clearTimers();
    }

    if (mode === 'observer' && observerText) {
      setText(observerText);
    } else {
      setText(pickCompletionPhrase());
    }

    fadeTimerRef.current = setTimeout(() => setFading(true), displayDurationMs - fadeDurationMs);
    timerRef.current = setTimeout(() => setText(''), displayDurationMs);

    return () => clearTimers();
  }, [mode, observerText, clearTimers, pickThinkingPhrase, pickCompletionPhrase, t, displayDurationMs, fadeDurationMs]);

  if (!text) return null;

  const isThinking = mode === 'thinking';

  return (
    <div
      className={cn(
        'absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap',
        'rounded-full px-2.5 py-0.5 text-xs font-medium',
        'border transition-opacity duration-300',
        isThinking ? 'border-border bg-muted text-muted-foreground' : 'border-primary/30 bg-primary/5 text-primary',
        fading && 'opacity-0',
      )}
    >
      {text}
    </div>
  );
}
