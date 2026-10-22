'use client';

/**
 * Capability Block Catalog Component for Visual Modular Agent Assembler.
 *
 * [INPUT] catalog: CapabilityBlock[], equippedBlockIds: string[], onAddBlock: (block: CapabilityBlock) => void
 * [OUTPUT] AssemblerBlockCatalog: Searchable and category-filtered tray of available building blocks.
 * [POS] src/components/features/agent-assembler/AssemblerBlockCatalog.tsx
 */

import { memo, useState, useMemo } from 'react';
import {
  Layers,
  Brain,
  Sparkles,
  Wrench,
  BookOpen,
  Database,
  ShieldCheck,
  Plus,
  Check,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { CapabilityBlock, CapabilityBlockCategory } from './assemblerTypes';

export interface AssemblerBlockCatalogProps {
  catalog: CapabilityBlock[];
  equippedBlockIds: string[];
  onAddBlock: (block: CapabilityBlock) => void;
  className?: string;
}

const CATEGORY_TABS: Array<{
  key: 'all' | CapabilityBlockCategory;
  labelKey: string;
  defaultLabel: string;
  icon: typeof Brain;
}> = [
  { key: 'all', labelKey: 'allCategories', defaultLabel: 'All', icon: Layers },
  { key: 'brain', labelKey: 'brain', defaultLabel: 'Brain', icon: Brain },
  { key: 'persona', labelKey: 'persona', defaultLabel: 'Persona', icon: Sparkles },
  { key: 'tools', labelKey: 'tools', defaultLabel: 'Tools', icon: Wrench },
  { key: 'skills', labelKey: 'skills', defaultLabel: 'Skills', icon: BookOpen },
  { key: 'memory', labelKey: 'memory', defaultLabel: 'Memory', icon: Database },
  { key: 'sandbox', labelKey: 'sandbox', defaultLabel: 'Sandbox', icon: ShieldCheck },
];

export const AssemblerBlockCatalog = memo(function AssemblerBlockCatalog({
  catalog,
  equippedBlockIds,
  onAddBlock,
  className,
}: AssemblerBlockCatalogProps) {
  const t = useTranslations('agentAssembler');
  const [selectedCategory, setSelectedCategory] = useState<'all' | CapabilityBlockCategory>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredBlocks = useMemo(() => {
    return catalog.filter((block) => {
      const matchCategory =
        selectedCategory === 'all' || block.category === selectedCategory;
      const matchQuery =
        !searchQuery ||
        block.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        block.description.toLowerCase().includes(searchQuery.toLowerCase());
      return matchCategory && matchQuery;
    });
  }, [catalog, selectedCategory, searchQuery]);

  return (
    <div
      className={cn(
        'flex flex-col h-full rounded-xl border border-border bg-card/60 backdrop-blur-sm overflow-hidden',
        className,
      )}
      data-testid="assembler-block-catalog"
    >
      {/* Header & Filter Tabs */}
      <div className="p-3 border-b border-border/60 bg-muted/20 flex flex-col gap-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-primary" />
            <span className="font-semibold text-xs text-foreground">
              {t('blockCatalogTitle') || 'Capability Blocks Pool'}
            </span>
          </div>
          <span className="text-[10px] text-muted-foreground font-mono">
            {filteredBlocks.length} {t('available') || 'blocks'}
          </span>
        </div>

        {/* Search */}
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
          }}
          placeholder={t('searchBlocks') || 'Search building blocks...'}
          className="w-full px-2.5 py-1 text-xs rounded-lg border border-border/80 bg-background/80 focus:outline-none focus:ring-1 focus:ring-primary/50 text-foreground placeholder:text-muted-foreground"
        />

        {/* Category Pills */}
        <div className="flex items-center gap-1 overflow-x-auto pb-0.5 no-scrollbar">
          {CATEGORY_TABS.map((tab) => {
            const Icon = tab.icon;
            const active = selectedCategory === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => {
                  setSelectedCategory(tab.key);
                }}
                className={cn(
                  'flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium whitespace-nowrap transition-colors border',
                  active
                    ? 'bg-primary text-primary-foreground border-primary shadow-xs'
                    : 'bg-muted/40 text-muted-foreground border-transparent hover:bg-muted hover:text-foreground',
                )}
              >
                <Icon className="h-3 w-3" />
                <span>{t(tab.labelKey) || tab.defaultLabel}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Blocks List */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {filteredBlocks.length > 0 ? (
          filteredBlocks.map((block) => {
            const isEquipped = equippedBlockIds.includes(block.id);
            return (
              <div
                key={block.id}
                className={cn(
                  'p-2.5 rounded-lg border transition-all duration-150 flex items-center justify-between gap-2',
                  isEquipped
                    ? 'bg-muted/30 border-border/60 opacity-75'
                    : 'bg-background border-border/80 hover:border-primary/50 hover:shadow-xs',
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-xs text-foreground truncate">
                      {block.name}
                    </span>
                    <span className="text-[9px] px-1 py-0.2 rounded bg-muted font-mono uppercase text-muted-foreground">
                      {block.category}
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-1">
                    {block.description}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    onAddBlock(block);
                  }}
                  disabled={isEquipped}
                  className={cn(
                    'flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-colors flex-shrink-0',
                    isEquipped
                      ? 'bg-muted text-muted-foreground cursor-not-allowed'
                      : 'bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs',
                  )}
                  title={isEquipped ? t('alreadyEquipped') || 'Equipped' : t('equip') || 'Equip'}
                >
                  {isEquipped ? (
                    <>
                      <Check className="h-3 w-3" />
                      <span>{t('equipped') || 'Equipped'}</span>
                    </>
                  ) : (
                    <>
                      <Plus className="h-3 w-3" />
                      <span>{t('equip') || 'Equip'}</span>
                    </>
                  )}
                </button>
              </div>
            );
          })
        ) : (
          <div className="text-center py-8 text-xs text-muted-foreground">
            {t('noBlocksFound') || 'No capability blocks found.'}
          </div>
        )}
      </div>
    </div>
  );
});
