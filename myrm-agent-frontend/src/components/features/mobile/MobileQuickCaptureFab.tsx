'use client';

/**
 * [INPUT]
 * - lucide-react::Sparkles (POS: Icons)
 * - next-intl::useTranslations (POS: Internationalization)
 *
 * [OUTPUT]
 * - MobileQuickCaptureFab: One-handed thumb-reachable floating action button on mobile hub.
 *
 * [POS]
 * Floating entry point anchored at the bottom-right corner for instant capture drawer invocation.
 */

import React from 'react';
import { Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';

export interface MobileQuickCaptureFabProps {
  onClick: () => void;
  className?: string;
}

export const MobileQuickCaptureFab: React.FC<MobileQuickCaptureFabProps> = ({
  onClick,
  className = '',
}) => {
  const t = useTranslations('mobile.quickCapture');

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="mobile-quick-capture-fab"
      aria-label={t('title')}
      className={`fixed bottom-6 right-5 z-40 flex items-center gap-1.5 px-3.5 py-2.5 rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/25 hover:bg-primary/90 active:scale-95 transition-all text-xs font-medium cursor-pointer ${className}`}
    >
      <Sparkles className="w-3.5 h-3.5" />
      <span>{t('title')}</span>
    </button>
  );
};
