/**
 * [INPUT]
 * - @/services/wikiService::writebackService (POS: 五层资产统计与分层词条查询服务)
 * - ./WikiReviewSlipModal (POS: 作者审阅单批量回写确认对话框)
 * - ./WikiLayerItemPreviewModal (POS: 词条 Markdown 只读预览模态框)
 * - ../WikiAgentScopeContext::useWikiAgentScope (POS: Agent Wiki 作用域上下文)
 *
 * [OUTPUT]
 * - WikiLayersLedgerPanel: 五层知识资产全局态势总览、分层下钻浏览与审阅单工作台面板
 *
 * [POS]
 * - 知识库全局资产态势展示与微观下钻层。展示 L1-L5 资产分布，提供下钻词条抽屉与审阅单回写入口。
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Layers,
  ShieldCheck,
  BrainCircuit,
  Compass,
  FileCheck2,
  FolderGit2,
  Sparkles,
  RefreshCw,
  HelpCircle,
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
import { WikiReviewSlipModal } from './WikiReviewSlipModal';
import { WikiLayerItemPreviewModal } from './WikiLayerItemPreviewModal';

interface WikiLayersLedgerPanelProps {
  onOpenConcept?: (relativePath: string) => void;
}

export function WikiLayersLedgerPanel({ onOpenConcept }: WikiLayersLedgerPanelProps = {}) {
  const { agentScopeId } = useWikiAgentScope();

  const [stats, setStats] = useState<WikiLayersStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);


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
      title: '原始输入与候选池',
      subtext: 'Raw & Inbox',
      icon: FolderGit2,
      count: (stats?.raw_files_count ?? 0) + (stats?.inbox_count ?? 0),
      badge: '原始存证',
      color: 'border-blue-500/30 text-blue-600 dark:text-blue-400 bg-blue-500/5',
      description: '未处理的网页快照、会议录音与瞬态草稿，严格不参与长期检索。',
    },
    {
      id: 'l2',
      targetKey: 'sources',
      layerNumber: 'L2',
      title: '来源凭证卡',
      subtext: 'Sources (身份证)',
      icon: ShieldCheck,
      count: stats?.sources_count ?? 0,
      badge: '证据来源',
      color: 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400 bg-emerald-500/5',
      description: '带有权威度与 SHA256 签名的来源身份卡，所有事实知识的追溯基石。',
    },
    {
      id: 'l3',
      targetKey: 'methods',
      layerNumber: 'L3',
      title: '核心知识体系',
      subtext: 'Concepts & Methods',
      icon: BrainCircuit,
      count: (stats?.concepts_count ?? 0) + (stats?.methods_count ?? 0),
      badge: '高可信真理',
      color: 'border-purple-500/30 text-purple-600 dark:text-purple-400 bg-purple-500/5',
      description: '客观事实、原子概念与工程方法论，通过 Draft-to-Live 严格门禁。',
    },
    {
      id: 'l4',
      targetKey: 'claims',
      layerNumber: 'L4',
      title: '观点与主张',
      subtext: 'Claims (待验证)',
      icon: Compass,
      count: stats?.claims_count ?? 0,
      badge: '主观推断',
      color: 'border-amber-500/30 text-amber-600 dark:text-amber-400 bg-amber-500/5',
      description: '带置信度与辩论记录的假说，与客观事实强行隔离，避免污染真理。',
    },
    {
      id: 'l5',
      targetKey: 'deliverables',
      layerNumber: 'L5',
      title: '交付物与使用台账',
      subtext: 'Deliverables & Ledgers',
      icon: FileCheck2,
      count: stats?.deliverables_count ?? 0,
      badge: '交付台账',
      color: 'border-rose-500/30 text-rose-600 dark:text-rose-400 bg-rose-500/5',
      description: '任务最终产出的交付物，完整记录知识引用、衍生与未采纳台账。',
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
                五层知识资产全局态势
                <Badge variant="outline" className="text-xs font-normal border-primary/30 text-primary">
                  WorkBuddy 架构
                </Badge>
              </CardTitle>
              <CardDescription className="text-sm text-muted-foreground mt-0.5">
                物理分层隔离事实与假说，提供任务台账审计与作者审阅单选择性回写机制。
              </CardDescription>
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
              刷新统计
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => setReviewModalOpen(true)}
              className="gap-1.5 h-8 text-xs shadow-sm"
            >
              <Sparkles className="w-3.5 h-3.5" />
              打开作者审阅单
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
                aria-label={`查看 ${layer.title} 词条清单`}
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
                    已归档条目
                    {isSelected && <ChevronDown className="w-3 h-3 text-primary animate-bounce" />}
                  </span>
                  <span className="text-lg font-bold font-mono text-foreground">
                    {loading ? '...' : layer.count}
                  </span>
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
                  {selectedLayerTitle} · 归档词条清单
                </h4>
                <Badge variant="secondary" className="text-xs font-mono">
                  {layerItems.length} 篇
                </Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedLayerId(null)}
                className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </Button>
            </div>

            {itemsLoading ? (
              <div className="py-8 text-center text-xs text-muted-foreground flex items-center justify-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-primary" />
                正在加载该层文档清单...
              </div>
            ) : layerItems.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground">
                当前层级暂无已归档的 Markdown 词条，完成长程任务后可通过审阅单回写生成。
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {layerItems.map((item) => (
                  <button
                    type="button"
                    key={item.relative_path}
                    aria-label={`预览词条 ${item.title}`}
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
                        {item.content_snippet || '暂无正文摘要'}
                      </p>
                    </div>

                    <div className="w-full mt-2.5 pt-2 border-t border-border/30 flex items-center justify-between text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1 font-mono truncate max-w-[160px]">
                        <Clock className="w-3 h-3 shrink-0" />
                        {item.updated_at ? item.updated_at.split('T')[0] : '刚刚'}
                        {item.source_task_id && (
                          <span className="text-[9px] text-primary/80 truncate">
                            #{item.source_task_id.slice(-4)}
                          </span>
                        )}
                      </span>
                      <span className="flex items-center gap-1 text-primary opacity-0 group-hover:opacity-100 transition-opacity font-medium">
                        <Eye className="w-3 h-3" />
                        快速预览
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="p-3 rounded-lg bg-secondary/30 border border-border/40 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
            <span>
              已激活<strong>负向不回写硬拦截</strong>：自动屏蔽演示环境、特定IP、一次性测试数据与临时脚本。
            </span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0 text-primary hover:underline cursor-pointer">
            <HelpCircle className="w-3.5 h-3.5" />
            <span>审阅单规范</span>
          </div>
        </div>
      </CardContent>

      <WikiReviewSlipModal
        open={reviewModalOpen}
        onOpenChange={setReviewModalOpen}
        onApplied={() => {
          void fetchStats();
          if (selectedLayerId) {
            void handleSelectLayer(selectedLayerId, selectedLayerKey, selectedLayerTitle);
          }
        }}
      />

      <WikiLayerItemPreviewModal
        item={previewItem}
        layerTitle={selectedLayerTitle}
        onClose={() => setPreviewItem(null)}
        onOpenInEditor={onOpenConcept}
      />
    </Card>
  );
}
