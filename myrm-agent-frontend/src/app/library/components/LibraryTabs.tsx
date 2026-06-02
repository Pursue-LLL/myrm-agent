'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { MessageSquare, Image, Zap, Network } from 'lucide-react';

export type LibraryTab = 'chats' | 'gallery' | 'skills' | 'graph';

interface LibraryTabsProps {
  activeTab: LibraryTab;
  onTabChange: (tab: LibraryTab) => void;
}

export default function LibraryTabs({ activeTab, onTabChange }: LibraryTabsProps) {
  const t = useTranslations('library');

  const tabs: { key: LibraryTab; icon: React.ReactNode; label: string }[] = [
    { key: 'chats', icon: <MessageSquare size={18} />, label: t('tabs.chats') },
    { key: 'gallery', icon: <Image size={18} />, label: t('tabs.gallery') },
    { key: 'skills', icon: <Zap size={18} />, label: t('tabs.skills') },
    { key: 'graph', icon: <Network size={18} />, label: t('tabs.graph') },
  ];

  return (
    <div className="flex border-b border-border mb-4">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onTabChange(tab.key)}
          className={cn(
            'flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors',
            'border-b-2 -mb-[1px]',
            activeTab === tab.key
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/30',
          )}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}
