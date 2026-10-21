import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Search, Archive, Download, RefreshCw, FolderOpen } from 'lucide-react';
import {
  fetchArtifactProvenance,
  type ArtifactCategory,
  type ArtifactProvenanceItem,
  type ArtifactCategoryStats,
} from '@/services/artifactProvenance';
import { ArtifactProvenanceCard } from './ArtifactProvenanceCard';

interface ArtifactsHubViewProps {
  initialChatId?: string;
  initialAgentId?: string;
  className?: string;
}

const CATEGORY_TABS: { key: ArtifactCategory; labelKey: string }[] = [
  { key: 'all', labelKey: 'tabAll' },
  { key: 'document', labelKey: 'tabDocument' },
  { key: 'code', labelKey: 'tabCode' },
  { key: 'data', labelKey: 'tabData' },
  { key: 'media', labelKey: 'tabMedia' },
  { key: 'link', labelKey: 'tabLink' },
  { key: 'other', labelKey: 'tabOther' },
];

export const ArtifactsHubView: React.FC<ArtifactsHubViewProps> = ({
  initialChatId,
  initialAgentId,
  className,
}) => {
  const t = useTranslations('artifacts.hub');
  const [activeTab, setActiveTab] = useState<ArtifactCategory>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [items, setItems] = useState<ArtifactProvenanceItem[]>([]);
  const [stats, setStats] = useState<ArtifactCategoryStats>({
    all: 0,
    document: 0,
    code: 0,
    data: 0,
    media: 0,
    link: 0,
    other: 0,
  });
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isExporting, setIsExporting] = useState(false);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetchArtifactProvenance({
        category: activeTab,
        query: searchQuery.trim() || undefined,
        chat_id: initialChatId,
        agent_id: initialAgentId,
        limit: 100,
      });
      setItems(res.items);
      setStats(res.stats);
    } catch (err) {
      console.error('Failed to fetch artifact provenance hub:', err);
    } finally {
      setIsLoading(false);
    }
  }, [activeTab, searchQuery, initialChatId, initialAgentId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map((i) => i.id)));
    }
  };

  const handleBatchExport = async () => {
    if (selectedIds.size === 0) {
      return;
    }
    setIsExporting(true);
    try {
      const response = await fetch('/api/v1/files/artifacts/download-bundle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artifact_ids: Array.from(selectedIds) }),
      });
      if (!response.ok) {
        throw new Error('Export bundle failed');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `artifacts-bundle-${new Date().toISOString().slice(0, 10)}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Batch export failed:', err);
    } finally {
      setIsExporting(false);
    }
  };

  const getTabCount = (tab: ArtifactCategory): number => {
    return stats[tab] ?? 0;
  };

  return (
    <div className={cn('flex flex-col h-full w-full bg-background', className)}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 sm:p-6 border-b border-border/60">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Archive className="w-6 h-6 text-primary" />
            <span>{t('title')}</span>
          </h2>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            {t('subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {selectedIds.size > 0 && (
            <button
              type="button"
              onClick={handleBatchExport}
              disabled={isExporting}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium',
                'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm transition-colors',
                isExporting && 'opacity-70 cursor-not-allowed',
              )}
            >
              <Download className={cn('w-3.5 h-3.5', isExporting && 'animate-bounce')} />
              <span>{t('exportZip')} ({selectedIds.size})</span>
            </button>
          )}

          <button
            type="button"
            onClick={loadData}
            disabled={isLoading}
            className="p-2 rounded-lg border border-border/60 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Refresh"
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Filter and Category Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 sm:px-6 py-3 border-b border-border/40 bg-muted/20">
        {/* Category Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {CATEGORY_TABS.map((tab) => {
            const count = getTabCount(tab.key);
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0',
                  isActive
                    ? 'bg-background text-foreground shadow-sm border border-border/80'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/60',
                )}
              >
                <span>{t(tab.labelKey)}</span>
                <span
                  className={cn(
                    'px-1.5 py-0.2 rounded-full text-[10px]',
                    isActive ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground',
                  )}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Search Input */}
        <div className="relative min-w-[220px] max-w-xs w-full">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className={cn(
              'w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-border/60 bg-background',
              'focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground',
            )}
          />
        </div>
      </div>

      {/* Content Grid */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <div className="w-12 h-12 rounded-2xl bg-muted/60 flex items-center justify-center text-muted-foreground mb-3">
              <FolderOpen className="w-6 h-6" />
            </div>
            <h3 className="font-semibold text-sm text-foreground mb-1">{t('emptyTitle')}</h3>
            <p className="text-xs text-muted-foreground max-w-sm">{t('emptyDesc')}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {items.map((item) => (
              <ArtifactProvenanceCard
                key={item.id}
                item={item}
                isSelected={selectedIds.has(item.id)}
                onToggleSelect={handleToggleSelect}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ArtifactsHubView;
