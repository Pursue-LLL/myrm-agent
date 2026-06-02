'use client';

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { ScanSearch } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';

const BrowserInspectorToggle: React.FC = () => {
  const t = useTranslations('chat.browserInspector');
  const { isBrowserActive, isOpen, togglePanel, viewData } = useBrowserInspectorStore();

  if (!isBrowserActive || !viewData) return null;

  return (
    <button
      type="button"
      onClick={togglePanel}
      className={cn(
        'fixed bottom-24 right-20 p-3 rounded-full shadow-lg transition-colors z-50',
        'flex items-center justify-center',
        'max-sm:bottom-20 max-sm:right-16',
        isOpen
          ? 'bg-primary text-primary-foreground ring-2 ring-primary/30'
          : 'bg-secondary text-secondary-foreground hover:bg-secondary/90',
      )}
      title={t('toggleTitle')}
      aria-label={t('toggleTitle')}
    >
      <ScanSearch size={22} />
    </button>
  );
};

export default React.memo(BrowserInspectorToggle);
