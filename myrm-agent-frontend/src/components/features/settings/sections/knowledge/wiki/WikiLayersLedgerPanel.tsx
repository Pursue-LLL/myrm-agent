/**
 * [INPUT]
 * - @/services/wikiService::writebackService (POS: 五层资产统计与分层词条查询服务)
 * - ./WikiLayerItemPreviewModal (POS: 词条 Markdown 只读预览模态框)
 * - ../WikiAgentScopeContext::useWikiAgentScope (POS: Agent Wiki 作用域上下文)
 * - next-intl::useTranslations (POS: Internationalization hook)
 *
 * [OUTPUT]
 * - WikiLayersLedgerPanel: 五层知识资产全局态势总览与分层下钻浏览面板
 *
 * [POS]
 * - 知识库全局资产态势展示与微观下钻层。展示 L1-L5 资产分布，提供下钻词条抽屉。
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Layers,
  ShieldCheck,
  BrainCircuit,
  Compass,
  FileCheck2,
  FolderGit2,
  RefreshCw,
  FileText,
  Clock,
  X,
  Eye,
  ChevronDown,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { writebackService, type WikiLayersStats, type WikiLayerItem } from '@/services/wikiService';
import { useWikiAgentScope } from '../WikiAgentScopeContext';
import { WikiLayerItemPreviewModal } from './WikiLayerItemPreviewModal';

interface WikiLayersLedgerPanelProps {
  onOpenConcept?: (relativePath: string) => void;
}

export function WikiLayersLedgerPanel({ onOpenConcept }: WikiLayersLedgerPanelProps = {}) {
  const t = useTranslations('settings.wiki.ledger');
  const { agentScopeId } = useWikiAgentScope();

  const [stats, setStats] = useState<WikiLayersStats | null>(null);
  const [loading, setLoading] = useState(false);

  // Micro-level layer item inspection state
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null);
  const [selectedLayerKey, setSelectedLayerKey] = useState<string>('methods');
  const [selectedLayerTitle, setSelectedLayerTitle] = useState<string>('');
  const [layerItems, setLayerItems] = useState<WikiLayerItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [previewItem, setPreviewItem] = useState<WikiLayerItem | null>(null);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    try {
      const data = await writebackService.getLayersStats(agentScopeId);
      setStats(data);
    } catch (err) {
      console.error('Failed to load wiki layer stats:', err);
    } finally {
      setLoading(false);
    }
  }, [agentScopeId]);

  const handleSelectLayer = useCallback(
    async (layerId: string, layerKey: string, layerTitle: string) => {
      if (selectedLayerId === layerId) {
        setSelectedLayerId(null);
        setLayerItems([]);
        return;
      }
      setSelectedLayerId(layerId);
      setSelectedLayerKey(layerKey);
      setSelectedLayerTitle(layerTitle);
      setItemsLoading(true);
      try {
        const items = await writebackService.getLayerItems(layerKey, agentScopeId);
        setLayerItems(items);
      } catch (err) {
        console.error('Failed to load layer items:', err);
        setLayerItems([]);
      } finally {
        setItemsLoading(false);
      }
    },
    [agentScopeId, selectedLayerId],
  );

  useEffect(() => {
    void fetchStats();
  }, [fetchStats]);

  const layersConfig = [
    {
      id: 'l1',
      targetKey: 'raw',
      layerNumber: 'L1',
      title: t('layers.l1.title'),
      subtext: t('layers.l1.subtext'),
      icon: FolderGit2,
      count: (stats?.raw_files_count ?? 0) + (stats?.inbox_count ?? 0),
      badge: t('layers.l1.badge'),
      color: 'border-blue-500/30 text-blue-600 dark:text-blue-400 bg-blue-500/5',
      description: t('layers.l1.description'),
    },
    {
      id: 'l2',
      targetKey: 'sources',
      layerNumber: 'L2',
      title: t('layers.l2.title'),
      subtext: t('layers.l2.subtext'),
      icon: ShieldCheck,
      count: stats?.sources_count ?? 0,
      badge: t('layers.l2.badge'),
      color: 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400 bg-emerald-500/5',
      description: t('layers.l2.description'),
    },
    {
      id: 'l3',
      targetKey: 'methods',
      layerNumber: 'L3',
      title: t('layers.l3.title'),
      subtext: t('layers.l3.subtext'),
      icon: BrainCircuit,
      count: (stats?.concepts_count ?? 0) + (stats?.methods_count ?? 0),
      badge: t('layers.l3.badge'),
      color: 'border-purple-500/30 text-purple-600 dark:text-purple-400 bg-purple-500/5',
      description: t('layers.l3.description'),
    },
    {
      id: 'l4',
      targetKey: 'claims',
      layerNumber: 'L4',
      title: t('layers.l4.title'),
      subtext: t('layers.l4.subtext'),
      icon: Compass,
      count: stats?.claims_count ?? 0,
      badge: t('layers.l4.badge'),
      color: 'border-amber-500/30 text-amber-600 dark:text-amber-400 bg-amber-500/5',
      description: t('layers.l4.description'),
    },
    {
      id: 'l5',
      targetKey: 'deliverables',
      layerNumber: 'L5',
      title: t('layers.l5.title'),
      subtext: t('layers.l5.subtext'),
      icon: FileCheck2,
      count: stats?.deliverables_count ?? 0,
      badge: t('layers.l5.badge'),
      color: 'border-rose-500/30 text-rose-600 dark:text-rose-400 bg-rose-500/5',
      description: t('layers.l5.description'),
    },
  ];

  return (
    <Card className="border border-border/60 bg-gradient-to-br from-card to-secondary/10 shadow-sm">
      <CardHeader className="pb-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-primary/10 text-primary border border-primary/20">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <CardTitle className="text-lg font-semibold tracking-tight flex items-center gap-2">
                {t('title')}
                <Badge variant="outline" className="text-xs font-normal border-primary/30 text-primary">
                  {t('architectureBadge')}
                </Badge>
              </CardTitle>
              <CardDescription className="text-sm text-muted-foreground mt-0.5">{t('description')}</CardDescription>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={fetchStats}
              disabled={loading}
              className="gap-1.5 h-8 text-xs border-border/60"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              {t('refreshStats')}
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Layer cards grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {layersConfig.map((layer) => {
            const Icon = layer.icon;
            const isSelected = selectedLayerId === layer.id;
            return (
              <button
                type="button"
                key={layer.id}
                aria-label={t('viewLayerItems', { title: layer.title })}
                onClick={() => void handleSelectLayer(layer.id, layer.targetKey, layer.title)}
                className={`text-left relative p-3.5 rounded-xl border ${layer.color} transition-all duration-200 cursor-pointer flex flex-col justify-between select-none ${
                  isSelected ? 'ring-2 ring-primary shadow-md scale-[1.01]' : 'hover:shadow-md hover:border-primary/40'
                }`}
              >
                <div className="w-full">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-xs font-mono font-bold px-1.5 py-0.5 rounded bg-background/80 border border-border/40">
                      {layer.layerNumber}
                    </span>
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                      {layer.badge}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <Icon className="w-4 h-4 shrink-0" />
                    <h4 className="text-sm font-semibold text-foreground truncate">{layer.title}</h4>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{layer.subtext}</p>
                  <p className="text-xs text-muted-foreground/80 mt-2 leading-relaxed line-clamp-3">
                    {layer.description}
                  </p>
                </div>

                <div className="mt-4 pt-2.5 border-t border-border/30 flex items-baseline justify-between">
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    {t('archivedItems')}
                    {isSelected && <ChevronDown className="w-3 h-3 text-primary animate-bounce" />}
                  </span>
                  <span className="text-lg font-bold font-mono text-foreground">{loading ? '...' : layer.count}</span>
                </div>
              </button>
            );
          })}
        </div>

        {/* Selected Layer Micro-level Inspection Drawer */}
        {selectedLayerId && (
          <div className="p-4 rounded-xl border border-border/60 bg-background/95 shadow-sm space-y-3 transition-all animate-in fade-in-50 duration-200">
            <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-primary" />
                <h4 className="text-sm font-semibold text-foreground">
                  {t('drawerTitle', { title: selectedLayerTitle })}
                </h4>
                <Badge variant="secondary" className="text-xs font-mono">
                  {t('itemCount', { count: layerItems.length })}
                </Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedLayerId(null)}
                aria-label={t('closeDrawer')}
                className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </Button>
            </div>

            {itemsLoading ? (
              <div className="py-8 text-center text-xs text-muted-foreground flex items-center justify-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-primary" />
                {t('loadingItems')}
              </div>
            ) : layerItems.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground">{t('emptyItems')}</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {layerItems.map((item) => (
                  <button
                    type="button"
                    key={item.relative_path}
                    aria-label={t('previewItem', { title: item.title })}
                    onClick={() => setPreviewItem(item)}
                    className="text-left group p-3 rounded-lg border border-border/50 bg-secondary/15 hover:bg-secondary/30 hover:border-primary/40 transition-all cursor-pointer flex flex-col justify-between select-none"
                  >
                    <div className="w-full">
                      <div className="flex items-center justify-between gap-1.5 mb-1.5">
                        <span className="text-xs font-medium text-foreground truncate group-hover:text-primary transition-colors">
                          {item.title}
                        </span>
                        <div className="flex items-center gap-1 shrink-0">
                          {item.file_type === 'json' && (
                            <Badge variant="default" className="text-[9px] px-1 py-0">
                              JSON
                            </Badge>
                          )}
                          <Badge
                            variant={item.publish_status === 'draft' ? 'outline' : 'secondary'}
                            className={`text-[10px] ${
                              item.publish_status === 'draft' ? 'border-amber-500/40 text-amber-500' : ''
                            }`}
                          >
                            {item.publish_status === 'draft' ? 'Draft' : 'Live'}
                          </Badge>
                        </div>
                      </div>
                      <p className="text-[11px] text-muted-foreground/80 line-clamp-2 leading-relaxed">
                        {item.content_snippet || t('noSnippet')}
                      </p>
                    </div>

                    <div className="w-full mt-2.5 pt-2 border-t border-border/30 flex items-center justify-between text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1 font-mono truncate max-w-[160px]">
                        <Clock className="w-3 h-3 shrink-0" />
                        {item.updated_at ? item.updated_at.split('T')[0] : t('justNow')}
                        {item.source_task_id && (
                          <span className="text-[9px] text-primary/80 truncate">#{item.source_task_id.slice(-4)}</span>
                        )}
                      </span>
                      <span className="flex items-center gap-1 text-primary opacity-0 group-hover:opacity-100 transition-opacity font-medium">
                        <Eye className="w-3 h-3" />
                        {t('quickPreview')}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>

      <WikiLayerItemPreviewModal
        item={previewItem}
        layerTitle={selectedLayerTitle}
        onClose={() => setPreviewItem(null)}
        onOpenInEditor={onOpenConcept}
      />
    </Card>
  );
}
