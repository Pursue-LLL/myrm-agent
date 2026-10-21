'use client';

/**
 * [INPUT]
 * - useWorkLayoutStore, ComputeTier from @/store/useWorkLayoutStore
 * - useTranslations from next-intl (namespace: 'workLayout')
 *
 * [OUTPUT]
 * - TurboProTierSelector: Model compute & reasoning tier switcher (Turbo vs Pro)
 *
 * [POS]
 * Compute tier selector embedded in message composer / header toolbar (Item 26).
 * Single file < 200 lines. Zero `any` types. Zero native emoji.
 */

import React, { useState, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Zap, Sparkles, Check, ChevronDown } from 'lucide-react';
import { useWorkLayoutStore, type ComputeTier } from '@/store/useWorkLayoutStore';

interface TurboProTierSelectorProps {
  className?: string;
  variant?: 'compact' | 'dropdown';
}

export function TurboProTierSelector({
  className = '',
  variant = 'compact',
}: TurboProTierSelectorProps) {
  const t = useTranslations('workLayout');
  const computeTier = useWorkLayoutStore((s) => s.computeTier);
  const setComputeTier = useWorkLayoutStore((s) => s.setComputeTier);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleOutsideClick);
    }
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [isOpen]);

  const handleSelect = (tier: ComputeTier) => {
    setComputeTier(tier);
    setIsOpen(false);
    window.dispatchEvent(
      new CustomEvent('myrm:compute-tier-changed', {
        detail: { tier },
      }),
    );
  };

  const isTurbo = computeTier === 'turbo';
  const isPro = computeTier === 'pro';

  if (variant === 'compact') {
    return (
      <div
        aria-label="Compute Tier"
        className={`inline-flex items-center rounded-xl bg-muted/60 p-0.5 border border-border/50 text-xs select-none ${className}`}
      >
        {/* Turbo Button */}
        <button
          type="button"
          aria-pressed={isTurbo}
          onClick={() => handleSelect('turbo')}
          title={t('computeTierTurboDesc')}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition-all ${
            isTurbo
              ? 'bg-background text-emerald-600 dark:text-emerald-400 shadow-xs ring-1 ring-border/40 font-semibold'
              : 'text-muted-foreground hover:text-foreground hover:bg-background/40'
          }`}
        >
          <Zap className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
          <span>{t('computeTierTurbo')}</span>
        </button>

        {/* Pro Button */}
        <button
          type="button"
          aria-pressed={isPro}
          onClick={() => handleSelect('pro')}
          title={t('computeTierProDesc')}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition-all ${
            isPro
              ? 'bg-background text-purple-600 dark:text-purple-400 shadow-xs ring-1 ring-border/40 font-semibold'
              : 'text-muted-foreground hover:text-foreground hover:bg-background/40'
          }`}
        >
          <Sparkles className="w-3.5 h-3.5 text-purple-500 shrink-0" />
          <span>{t('computeTierPro')}</span>
        </button>
      </div>
    );
  }

  // Dropdown Variant
  return (
    <div ref={popoverRef} className={`relative inline-block ${className}`}>
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-xl bg-muted/70 hover:bg-muted border border-border/60 transition-all text-foreground"
      >
        {isTurbo ? (
          <Zap className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
        ) : (
          <Sparkles className="w-3.5 h-3.5 text-purple-500 shrink-0" />
        )}
        <span className="font-medium">
          {isTurbo ? t('computeTierTurbo') : t('computeTierPro')}
        </span>
        <ChevronDown className="w-3 h-3 text-muted-foreground ml-0.5" />
      </button>

      {isOpen && (
        <div
          aria-label="Compute Tier Options"
          className="absolute right-0 top-full mt-1.5 w-60 rounded-2xl bg-card border border-border shadow-xl backdrop-blur-md p-1.5 z-50 flex flex-col gap-1 select-none animate-in fade-in zoom-in-95 duration-100"
        >
          {/* Turbo Item */}
          <button
            type="button"
            onClick={() => handleSelect('turbo')}
            className={`flex items-start gap-2.5 p-2 rounded-xl text-left transition-all ${
              isTurbo ? 'bg-primary/10 text-foreground' : 'hover:bg-muted/60 text-foreground/80'
            }`}
          >
            <div className="w-6 h-6 rounded-lg bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0 mt-0.5">
              <Zap className="w-3.5 h-3.5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs text-foreground">{t('computeTierTurbo')}</span>
                {isTurbo && <Check className="w-3.5 h-3.5 text-primary" />}
              </div>
              <p className="text-[11px] text-muted-foreground leading-snug mt-0.5">
                {t('computeTierTurboDesc')}
              </p>
            </div>
          </button>

          {/* Pro Item */}
          <button
            type="button"
            onClick={() => handleSelect('pro')}
            className={`flex items-start gap-2.5 p-2 rounded-xl text-left transition-all ${
              isPro ? 'bg-primary/10 text-foreground' : 'hover:bg-muted/60 text-foreground/80'
            }`}
          >
            <div className="w-6 h-6 rounded-lg bg-purple-500/10 text-purple-500 flex items-center justify-center shrink-0 mt-0.5">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs text-foreground">{t('computeTierPro')}</span>
                {isPro && <Check className="w-3.5 h-3.5 text-primary" />}
              </div>
              <p className="text-[11px] text-muted-foreground leading-snug mt-0.5">
                {t('computeTierProDesc')}
              </p>
            </div>
          </button>
        </div>
      )}
    </div>
  );
}
