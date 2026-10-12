'use client';

/**
 * [INPUT]
 * @/services/memory/conversationLineageDefense::searchWithLineageDefense, getLineageDefenseStats,
 *   HydratedHitDTO, LineageDedupAuditReportDTO, LineageDefenseSearchRequestDTO
 * ./ConversationLineageDedupView::ConversationLineageDedupView
 * ./AutomationDemotionAuditConsoleView::AutomationDemotionAuditConsoleView
 *
 * [OUTPUT]
 * ConversationLineageDefenseCard: Command center card providing HUD metrics, source-aware
 * demotion tuning, generational lineage deduplication, and asymmetric progressive window hydration.
 *
 * [POS]
 * Primary UI Card for Item 97 (LineageDedupRecallBlindnessDefenseAndAutomationDemotionSuite).
 * Strict typing applied: No `any` types allowed. Single file < 400 lines.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import {
  GitFork,
  RefreshCw,
  Search,
  Sparkles,
  TrendingDown,
  UserCheck,
  Clock,
  Layers,
} from 'lucide-react';
import {
  getLineageDefenseStats,
  searchWithLineageDefense,
  type HydratedHitDTO,
  type LineageDedupAuditReportDTO,
  type LineageDefenseSearchRequestDTO,
} from '@/services/memory/conversationLineageDefense';
import { ConversationLineageDedupView } from './ConversationLineageDedupView';
import { AutomationDemotionAuditConsoleView } from './AutomationDemotionAuditConsoleView';

type ActiveTab = 'demotion_search' | 'lineage_dedup';

const FALLBACK_HITS: HydratedHitDTO[] = [
  {
    session_id: 'chat_auth_refactor_v2',
    lineage_root_id: 'root_auth_refactor',
    title: 'Authentication Middleware Implementation Compaction v2',
    source_kind: 'interactive',
    detail_level: 'expanded_window',
    content_snippet: 'Dependency get_current_user implemented with full 401 handling.',
    window_messages: [
      'SUMMARY: Previous round decided on 24h HMAC tokens.',
      "USER: Let's write the FastAPI dependency and unit tests.",
      'AGENT: Dependency get_current_user implemented with full 401 handling.',
    ],
    token_estimate: 42,
    is_demoted: false,
    is_lineage_primary: true,
    collapsed_generations_count: 1,
    collapsed_session_ids: ['chat_auth_refactor_v1'],
  },
  {
    session_id: 'cron_hourly_db_vacuum',
    lineage_root_id: 'cron_hourly_db_vacuum',
    title: 'Scheduled Database Vacuum & Health Check',
    source_kind: 'cron',
    detail_level: 'compact_card',
    content_snippet: 'Processed 128 SQLite memory tables without error.',
    window_messages: [],
    token_estimate: 14,
    is_demoted: true,
    is_lineage_primary: true,
    collapsed_generations_count: 0,
    collapsed_session_ids: [],
  },
];

export function ConversationLineageDefenseCard(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<ActiveTab>('demotion_search');
  const [hits, setHits] = useState<HydratedHitDTO[]>(FALLBACK_HITS);
  const [auditReport, setAuditReport] = useState<LineageDedupAuditReportDTO | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setStatusMessage(null);
    try {
      const res = await searchWithLineageDefense({
        query: 'authentication token validation',
        include_internal: false,
        cron_weight_multiplier: 0.45,
      });
      if (res?.hits) {
        setHits(res.hits);
        setAuditReport(res.audit_report ?? null);
      }
    } catch {
      setAuditReport(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleExecuteSearch = async (request: LineageDefenseSearchRequestDTO): Promise<void> => {
    try {
      const res = await searchWithLineageDefense(request);
      setHits(res.hits);
      setAuditReport(res.audit_report);
      setStatusMessage(
        `防盲区检索完成：召回 ${res.hits.length} 项有效代表，Token 节约 ${res.audit_report.token_saving_percent}%`
      );
    } catch {
      setStatusMessage('已使用本地模拟检索结果');
    }
  };

  return (
    <Card
      className="border border-border/80 bg-card/60 shadow-sm"
      data-testid="conversation-lineage-defense-card"
    >
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-primary/10 p-2 text-primary">
              <GitFork className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base font-semibold text-foreground">
                  会话血统代际去重与自动化降权套件
                </CardTitle>
                <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20 text-[10px]">
                  Item 97 P0
                </Badge>
              </div>
              <CardDescription className="text-xs text-muted-foreground mt-0.5">
                深度汲取 Hermes Agent PR #19434：来源感知降权破除高频 Cron 召回盲区、血统根去重消除多代冗余、非对称渐进水合削减 70%+ Token
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={fetchData}
              disabled={loading}
              aria-label="刷新血统防御与检索状态"
              className="h-8 gap-1 text-xs focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </Button>
          </div>
        </div>

        {/* HUD Indicator Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <div className="flex items-center justify-between text-muted-foreground text-[11px]">
              <span>交互置顶优先率</span>
              <UserCheck className="w-3.5 h-3.5 text-blue-500" />
            </div>
            <div className="text-lg font-bold text-foreground mt-0.5" data-testid="hud-interactive-ratio">
              {auditReport != null
                ? `${(auditReport.interactive_top1_ratio * 100).toFixed(0)}%`
                : '—'}
            </div>
          </div>

          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <div className="flex items-center justify-between text-muted-foreground text-[11px]">
              <span>Cron 自动化降权</span>
              <Clock className="w-3.5 h-3.5 text-amber-500" />
            </div>
            <div className="text-lg font-bold text-amber-600 mt-0.5" data-testid="hud-cron-demoted">
              {auditReport != null ? `${auditReport.demoted_cron_count} 项` : '—'}
            </div>
          </div>

          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <div className="flex items-center justify-between text-muted-foreground text-[11px]">
              <span>血统代际折叠数</span>
              <Layers className="w-3.5 h-3.5 text-purple-500" />
            </div>
            <div className="text-lg font-bold text-foreground mt-0.5" data-testid="hud-lineage-collapsed">
              {auditReport != null ? `${auditReport.collapsed_lineage_count} 代` : '—'}
            </div>
          </div>

          <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
            <div className="flex items-center justify-between text-muted-foreground text-[11px]">
              <span>Token 节约率</span>
              <TrendingDown className="w-3.5 h-3.5 text-emerald-500" />
            </div>
            <div className="text-lg font-bold text-emerald-600 mt-0.5" data-testid="hud-token-savings">
              {auditReport != null ? `${auditReport.token_saving_percent}%` : '—'}
            </div>
          </div>
        </div>

        {/* Status Alert */}
        {statusMessage && (
          <div className="mt-2 rounded-md bg-primary/10 border border-primary/20 px-3 py-1.5 text-xs text-primary flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              {statusMessage}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setStatusMessage(null)}
              aria-label="关闭提示"
              className="h-5 px-1 text-[11px] text-primary/70 hover:text-primary"
            >
              关闭
            </Button>
          </div>
        )}

        {/* Tab Controls */}
        <div className="flex items-center gap-1.5 pt-2 border-b border-border/50">
          <button
            type="button"
            onClick={() => setActiveTab('demotion_search')}
            aria-label="自动化降权与水合检索"
            className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'demotion_search'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
            data-testid="tab-demotion-search"
          >
            <Search className="w-3.5 h-3.5" />
            自动化降权与水合检索
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('lineage_dedup')}
            aria-label="会话血统代际去重谱系"
            className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'lineage_dedup'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
            data-testid="tab-lineage-dedup"
          >
            <GitFork className="w-3.5 h-3.5 text-primary" />
            会话血统代际去重谱系 ({hits.length})
          </button>
        </div>
      </CardHeader>

      <CardContent className="pt-2">
        {activeTab === 'demotion_search' ? (
          <AutomationDemotionAuditConsoleView
            hits={hits}
            auditReport={auditReport}
            onExecuteSearch={handleExecuteSearch}
          />
        ) : (
          <ConversationLineageDedupView hits={hits} />
        )}
      </CardContent>
    </Card>
  );
}
