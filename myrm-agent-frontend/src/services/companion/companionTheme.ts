import { useEffect, useState } from 'react';

import type { Rarity } from '@/components/features/companion/companionGenerator';
import { THEME_PREINIT_STORAGE_KEY } from '@/theme-engine/preinit';

export interface CompanionRarityVisual {
  textColor: string | null;
  glowFilter: string;
  ringShadow: string;
}

export interface CompanionBubbleToneVisual {
  borderColor: string;
  textColor: string;
}

const RARITY_TOKEN_VAR: Record<Exclude<Rarity, 'Common'>, string> = {
  Uncommon: '--primary',
  Rare: '--primary-hover',
  Epic: '--accent-warm',
  Legendary: '--accent-warm',
};

const RARITY_GLOW: Record<Exclude<Rarity, 'Common'>, { blur: number; alpha: number }> = {
  Uncommon: { blur: 4, alpha: 0.3 },
  Rare: { blur: 6, alpha: 0.4 },
  Epic: { blur: 8, alpha: 0.5 },
  Legendary: { blur: 12, alpha: 0.6 },
};

export function readThemeCssVar(name: string): string {
  if (typeof window === 'undefined') {
    return '';
  }
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function colorMixAlpha(color: string, alpha: number): string {
  const pct = Math.round(alpha * 100);
  return `color-mix(in srgb, ${color} ${pct}%, transparent)`;
}

export function resolveCompanionRarityVisual(rarity: Rarity): CompanionRarityVisual {
  if (rarity === 'Common') {
    return { textColor: null, glowFilter: '', ringShadow: '' };
  }

  const tokenVar = RARITY_TOKEN_VAR[rarity];
  const color = readThemeCssVar(tokenVar);
  if (!color) {
    return { textColor: null, glowFilter: '', ringShadow: '' };
  }

  const { blur, alpha } = RARITY_GLOW[rarity];
  const glowFilter =
    rarity === 'Legendary'
      ? `drop-shadow(0 0 ${blur}px ${colorMixAlpha(color, alpha)}) drop-shadow(0 0 ${blur * 2}px ${colorMixAlpha(color, alpha * 0.5)})`
      : `drop-shadow(0 0 ${blur}px ${colorMixAlpha(color, alpha)})`;

  const ringShadow =
    rarity === 'Epic'
      ? `0 0 0 1px ${colorMixAlpha(color, 0.3)}`
      : rarity === 'Legendary'
        ? `0 0 0 2px ${colorMixAlpha(color, 0.4)}`
        : '';

  return { textColor: color, glowFilter, ringShadow };
}

export function resolveCompanionBubbleTone(tone: 'wait' | 'error' | 'neutral'): CompanionBubbleToneVisual {
  if (tone === 'wait') {
    const warm = readThemeCssVar('--accent-warm');
    return {
      borderColor: warm ? colorMixAlpha(warm, 0.4) : 'color-mix(in srgb, var(--accent-warm) 40%, transparent)',
      textColor: warm || 'var(--foreground)',
    };
  }
  if (tone === 'error') {
    const destructive = readThemeCssVar('--destructive');
    return {
      borderColor: destructive
        ? colorMixAlpha(destructive, 0.4)
        : 'color-mix(in srgb, var(--destructive) 40%, transparent)',
      textColor: destructive || 'var(--destructive)',
    };
  }
  return {
    borderColor: 'color-mix(in srgb, var(--border) 60%, transparent)',
    textColor: 'var(--foreground)',
  };
}

/** Re-render companion accents when workspace theme tokens change. */
export function useCompanionThemeEpoch(): number {
  const [epoch, setEpoch] = useState(0);

  useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => {
      setEpoch((value) => value + 1);
    });
    observer.observe(root, {
      attributes: true,
      attributeFilter: ['data-myrm-theme-profile', 'class'],
    });

    const onStorage = (event: StorageEvent) => {
      if (event.key === THEME_PREINIT_STORAGE_KEY) {
        setEpoch((value) => value + 1);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => {
      observer.disconnect();
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  return epoch;
}
