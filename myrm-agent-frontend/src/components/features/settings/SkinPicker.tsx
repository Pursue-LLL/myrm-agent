/**
 * [INPUT] 'next-intl'::useTranslations (POS: i18n翻译)
 * [INPUT] '@/lib/utils/classnameUtils'::cn (POS: 样式合并工具)
 * [OUTPUT] SkinPicker: 品牌皮肤选择器组件，支持6套预设强调色方案。
 * [POS] 设置页外观子组件。通过 data-skin CSS属性切换全局强调色主题，持久化到 localStorage。
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

type SkinId = 'default' | 'teal' | 'rose' | 'amber' | 'violet' | 'ocean';

interface SkinOption {
  id: SkinId;
  lightAccent: string;
  darkAccent: string;
  lightWarm?: string;
  darkWarm?: string;
}

const SKINS: SkinOption[] = [
  { id: 'default', lightAccent: '#588e95', darkAccent: '#6ba3aa', lightWarm: '#e07830', darkWarm: '#f5b868' },
  { id: 'teal', lightAccent: '#588e95', darkAccent: '#6ba3aa' },
  { id: 'rose', lightAccent: '#c4567a', darkAccent: '#f472b6' },
  { id: 'amber', lightAccent: '#b4762c', darkAccent: '#fbbf24' },
  { id: 'violet', lightAccent: '#7c4dba', darkAccent: '#a78bfa' },
  { id: 'ocean', lightAccent: '#2563eb', darkAccent: '#60a5fa' },
];

const SKIN_STORAGE_KEY = 'myrm-skin';

function applySkin(skin: SkinId) {
  if (skin === 'default') {
    document.documentElement.removeAttribute('data-skin');
  } else {
    document.documentElement.setAttribute('data-skin', skin);
  }
}

function getStoredSkin(): SkinId {
  if (typeof window === 'undefined') return 'default';
  return (localStorage.getItem(SKIN_STORAGE_KEY) as SkinId) || 'default';
}

const SkinPicker = ({ className }: { className?: string }) => {
  const t = useTranslations('settings.skinOptions');
  const [mounted, setMounted] = useState(false);
  const [activeSkin, setActiveSkin] = useState<SkinId>('default');

  useEffect(() => {
    const stored = getStoredSkin();
    setActiveSkin(stored);
    applySkin(stored);
    setMounted(true);
  }, []);

  const handleSelect = useCallback((skin: SkinId) => {
    setActiveSkin(skin);
    applySkin(skin);
    localStorage.setItem(SKIN_STORAGE_KEY, skin);
  }, []);

  if (!mounted) return null;

  const isDark = document.documentElement.classList.contains('dark');

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {SKINS.map((skin) => {
        const isDual = skin.id === 'default';
        const main = isDark ? skin.darkAccent : skin.lightAccent;
        const warm = isDual ? (isDark ? skin.darkWarm : skin.lightWarm) : undefined;

        return (
          <button
            key={skin.id}
            onClick={() => handleSelect(skin.id)}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all border',
              activeSkin === skin.id
                ? 'border-primary bg-primary/10 text-foreground ring-1 ring-accent-warm/35 shadow-brand'
                : 'border-border bg-secondary/40 text-muted-foreground hover:bg-secondary hover:text-foreground',
            )}
          >
            <span
              className={cn(
                'w-4 h-4 rounded-full shrink-0 ring-1 ring-black/10 dark:ring-white/10 overflow-hidden',
                isDual ? 'flex' : 'block',
              )}
              aria-hidden
            >
              {isDual && warm ? (
                <>
                  <span className="w-1/2 h-full" style={{ backgroundColor: main }} />
                  <span className="w-1/2 h-full" style={{ backgroundColor: warm }} />
                </>
              ) : (
                <span className="block w-full h-full" style={{ backgroundColor: main }} />
              )}
            </span>
            {t(skin.id)}
          </button>
        );
      })}
    </div>
  );
};

export default SkinPicker;
