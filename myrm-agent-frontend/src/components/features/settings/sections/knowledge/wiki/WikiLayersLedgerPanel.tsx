'use client';

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
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { writebackService, type WikiLayersStats } from '@/services/wikiService';
import { useWikiAgentScope } from '../WikiAgentScopeContext';
import { WikiReviewSlipModal } from './WikiReviewSlipModal';

export function WikiLayersLedgerPanel() {
  const { agentScopeId } = useWikiAgentScope();

  const [stats, setStats] = useState<WikiLayersStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);

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

  useEffect(() => {
    void fetchStats();
  }, [fetchStats]);

  const layersConfig = [
    {
      id: 'l1',
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {layersConfig.map((layer) => {
            const Icon = layer.icon;
            return (
              <div
                key={layer.id}
                className={`relative p-3.5 rounded-xl border ${layer.color} transition-all duration-200 hover:shadow-md flex flex-col justify-between`}
              >
                <div>
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
                  <span className="text-xs text-muted-foreground">已归档条目</span>
                  <span className="text-lg font-bold font-mono text-foreground">
                    {loading ? '...' : layer.count}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

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
        }}
      />
    </Card>
  );
}
