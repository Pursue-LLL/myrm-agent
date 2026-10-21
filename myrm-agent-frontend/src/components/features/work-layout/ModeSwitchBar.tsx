'use client';

/**
 * [INPUT]
 * - useWorkLayoutStore from @/store/useWorkLayoutStore
 * - useTranslations from next-intl (namespace: 'workLayout')
 *
 * [OUTPUT]
 * - ModeSwitchBar: Smooth sliding toggle for Chat Mode vs Work Mode with Mod+Shift+M hotkey
 *
 * [POS]
 * Dual-Mode layout header switch controller (Item 26).
 * Single file < 160 lines. Zero `any` types. Zero native emoji.
 */

import React, { useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { MessageSquare, Briefcase } from 'lucide-react';
import { useWorkLayoutStore, type ViewMode } from '@/store/useWorkLayoutStore';

interface ModeSwitchBarProps {
  className?: string;
  size?: 'sm' | 'md';
}

export function ModeSwitchBar({ className = '', size = 'md' }: ModeSwitchBarProps) {
  const t = useTranslations('workLayout');
  const viewMode = useWorkLayoutStore((s) => s.viewMode);
  const setViewMode = useWorkLayoutStore((s) => s.setViewMode);
  const toggleViewMode = useWorkLayoutStore((s) => s.toggleViewMode);

  // Global keyboard shortcut: Mod+Shift+M (Cmd+Shift+M or Ctrl+Shift+M)
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === 'M' || e.key === 'm')) {
        e.preventDefault();
        toggleViewMode();
      }
    },
    [toggleViewMode],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const isChat = viewMode === 'chat';
  const isWork = viewMode === 'work';

  const containerPadding = size === 'sm' ? 'p-0.5' : 'p-1';
  const buttonPadding = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-1.5 text-xs';
  const iconSize = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4';

  return (
    <div
      aria-label={t('modeSwitchTooltip')}
      className={`inline-flex items-center rounded-2xl bg-muted/70 p-1 border border-border/60 shadow-xs backdrop-blur-xs select-none transition-all ${containerPadding} ${className}`}
    >
      {/* Chat Mode Option */}
      <button
        type="button"
        aria-pressed={isChat}
        onClick={() => setViewMode('chat')}
        className={`flex items-center gap-1.5 rounded-xl font-medium transition-all ${buttonPadding} ${
          isChat
            ? 'bg-background text-foreground shadow-xs ring-1 ring-border/50'
            : 'text-muted-foreground hover:text-foreground hover:bg-background/40'
        }`}
      >
        <MessageSquare className={`${iconSize} ${isChat ? 'text-primary' : 'text-muted-foreground'}`} />
        <span>{t('modeChat')}</span>
      </button>

      {/* Work Mode Option */}
      <button
        type="button"
        aria-pressed={isWork}
        onClick={() => setViewMode('work')}
        className={`flex items-center gap-1.5 rounded-xl font-medium transition-all ${buttonPadding} ${
          isWork
            ? 'bg-background text-foreground shadow-xs ring-1 ring-border/50'
            : 'text-muted-foreground hover:text-foreground hover:bg-background/40'
        }`}
      >
        <Briefcase className={`${iconSize} ${isWork ? 'text-primary' : 'text-muted-foreground'}`} />
        <span>{t('modeWork')}</span>
      </button>
    </div>
  );
}
