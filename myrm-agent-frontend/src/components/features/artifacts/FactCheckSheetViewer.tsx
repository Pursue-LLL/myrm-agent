'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  ShieldAlert,
  AlertTriangle,
  Info,
  CheckCircle2,
  HelpCircle,
  GitFork,
  Search,
  Scale,
  FileText,
  ChevronDown,
  ChevronUp,
  X,
  FileCheck,
} from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { FactCheckSheet, FactCheckItem, ConflictSeverity, ResolutionStatus } from './deliverableTypes';
import { getApiUrl } from '@/lib/api';

interface FactCheckSheetViewerProps {
  sheet?: FactCheckSheet | null;
  vaultUri?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
}

export const FactCheckSheetViewer: React.FC<FactCheckSheetViewerProps> = ({
  sheet: propSheet,
  vaultUri,
  open,
  onOpenChange,
  title,
}) => {
  const t = useTranslations('artifacts.factCheck');
  const [data, setData] = useState<FactCheckSheet | null>(propSheet || null);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set());

  // 同步外部传入的 sheet 对象
  useEffect(() => {
    if (propSheet) {
      setData(propSheet);
    }
  }, [propSheet]);

  // 若未传入 sheet 但提供了 vaultUri，则自动从 Vault 读取
  useEffect(() => {
    if (!propSheet && vaultUri && open) {
      const cleanId = vaultUri.replace('vault://', '');
      setLoading(true);
      fetch(`${getApiUrl()}/api/v1/files/vault/${cleanId}`)
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error('Failed to fetch'))))
        .then((parsed: FactCheckSheet) => {
          setData(parsed);
          setLoading(false);
        })
        .catch(() => {
          setLoading(false);
        });
    }
  }, [propSheet, vaultUri, open]);

  // 默认展开所有条目
  useEffect(() => {
    if (data?.items) {
      setExpandedItemIds(new Set(data.items.map((i) => i.id)));
    }
  }, [data]);

  const toggleExpand = (id: string) => {
    setExpandedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const filteredItems = useMemo(() => {
    if (!data?.items) return [];
    return data.items.filter((item) => {
      const matchSeverity = severityFilter === 'all' || item.severity === severityFilter;
      const kw = searchKeyword.toLowerCase();
      const matchKw =
        !kw ||
        item.claim_topic.toLowerCase().includes(kw) ||
        item.adopted_value.toLowerCase().includes(kw) ||
        item.resolution_rationale.toLowerCase().includes(kw) ||
        item.sources.some(
          (s) => s.document_title.toLowerCase().includes(kw) || s.claimed_value.toLowerCase().includes(kw),
        );
      return matchSeverity && matchKw;
    });
  }, [data, severityFilter, searchKeyword]);

  const counts = useMemo(() => {
    if (!data?.items) return { total: 0, critical: 0, warning: 0, info: 0, unresolved: 0 };
    return {
      total: data.items.length,
      critical: data.items.filter((i) => i.severity === 'critical').length,
      warning: data.items.filter((i) => i.severity === 'warning').length,
      info: data.items.filter((i) => i.severity === 'info').length,
      unresolved: data.items.filter((i) => i.status === 'unresolved').length,
    };
  }, [data]);

  const renderSeverityBadge = (severity: ConflictSeverity) => {
    switch (severity) {
      case 'critical':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
            <ShieldAlert className="w-3 h-3" />
            {t('criticalConflicts')}
          </span>
        );
      case 'warning':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            <AlertTriangle className="w-3 h-3" />
            {t('warnings')}
          </span>
        );
      case 'info':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20">
            <Info className="w-3 h-3" />
            {t('infoDifferences')}
          </span>
        );
    }
  };

  const renderStatusBadge = (status: ResolutionStatus) => {
    switch (status) {
      case 'resolved':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" />
            {t('statusResolved')}
          </span>
        );
      case 'unresolved':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            <HelpCircle className="w-3 h-3" />
            {t('statusUnresolved')}
          </span>
        );
      case 'conditional':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400 border border-violet-500/20">
            <GitFork className="w-3 h-3" />
            {t('statusConditional')}
          </span>
        );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[85vh] flex flex-col p-0 overflow-hidden bg-background">
        {/* Header */}
        <DialogHeader className="p-6 pb-4 border-b bg-muted/20 flex flex-row items-center justify-between">
          <div className="space-y-1">
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <Scale className="w-6 h-6 text-primary" />
              {title || data?.title || t('title')}
            </DialogTitle>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="text-xs text-muted-foreground">
                {t('totalItems')}: <strong className="text-foreground">{counts.total}</strong>
              </span>
              <span className="text-muted-foreground/40">|</span>
              <span className="text-xs text-rose-600 dark:text-rose-400 font-medium">
                {t('criticalConflicts')}: {counts.critical}
              </span>
              <span className="text-muted-foreground/40">|</span>
              <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
                {t('warnings')}: {counts.warning}
              </span>
              {counts.unresolved > 0 && (
                <>
                  <span className="text-muted-foreground/40">|</span>
                  <span className="text-xs text-orange-600 dark:text-orange-400 font-medium">
                    {t('unresolvedItems')}: {counts.unresolved}
                  </span>
                </>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* Filter Toolbar */}
        <div className="px-6 py-3 border-b flex flex-wrap items-center justify-between gap-3 bg-background">
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant={severityFilter === 'all' ? 'default' : 'outline'}
              onClick={() => setSeverityFilter('all')}
              className="rounded-full text-xs h-7"
            >
              {t('filterAll')} ({counts.total})
            </Button>
            {counts.critical > 0 && (
              <Button
                size="sm"
                variant={severityFilter === 'critical' ? 'default' : 'outline'}
                onClick={() => setSeverityFilter('critical')}
                className="rounded-full text-xs h-7 text-rose-600 dark:text-rose-400"
              >
                {t('filterCritical')} ({counts.critical})
              </Button>
            )}
            {counts.warning > 0 && (
              <Button
                size="sm"
                variant={severityFilter === 'warning' ? 'default' : 'outline'}
                onClick={() => setSeverityFilter('warning')}
                className="rounded-full text-xs h-7 text-amber-600 dark:text-amber-400"
              >
                {t('filterWarning')} ({counts.warning})
              </Button>
            )}
          </div>

          <div className="relative w-64">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="h-8 pl-8 text-xs"
            />
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loading && <div className="py-20 text-center text-xs text-muted-foreground">{t('loading')}</div>}

          {!loading && data?.summary && (
            <div className="p-4 rounded-xl border border-primary/20 bg-primary/5 text-xs text-foreground/90 space-y-1">
              <h4 className="font-semibold flex items-center gap-1.5 text-primary">
                <FileCheck className="w-4 h-4" />
                {t('summaryTitle')}
              </h4>
              <p className="leading-relaxed whitespace-pre-wrap">{data.summary}</p>
            </div>
          )}

          {!loading &&
            filteredItems.map((item) => {
              const isExpanded = expandedItemIds.has(item.id);
              return (
                <div key={item.id} className="border rounded-xl bg-card transition-all shadow-sm overflow-hidden">
                  {/* Item Header */}
                  <div
                    onClick={() => toggleExpand(item.id)}
                    className="p-4 cursor-pointer flex items-center justify-between gap-3 hover:bg-muted/30 transition-colors"
                  >
                    <div className="flex items-center gap-2.5 flex-1 min-w-0">
                      {renderSeverityBadge(item.severity)}
                      <h4 className="font-semibold text-sm text-foreground truncate">{item.claim_topic}</h4>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {renderStatusBadge(item.status)}
                      <span className="text-[11px] font-mono text-muted-foreground">
                        {t('confidence')}: {(item.confidence_score * 100).toFixed(0)}%
                      </span>
                      {isExpanded ? (
                        <ChevronUp className="w-4 h-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-muted-foreground" />
                      )}
                    </div>
                  </div>

                  {/* Item Expanded Details */}
                  {isExpanded && (
                    <div className="px-4 pb-4 pt-1 space-y-3 border-t bg-muted/10">
                      {/* Adopted Value & Rationale */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                        <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                          <span className="text-[11px] font-medium text-emerald-700 dark:text-emerald-300 block mb-1">
                            {t('adoptedStandard')}
                          </span>
                          <p className="text-sm font-semibold text-foreground font-mono">{item.adopted_value}</p>
                        </div>

                        <div className="p-3 rounded-lg bg-muted/40 border">
                          <span className="text-[11px] font-medium text-muted-foreground block mb-1">
                            {t('rationale')}
                          </span>
                          <p className="text-xs text-foreground/90 leading-relaxed">{item.resolution_rationale}</p>
                        </div>
                      </div>

                      {/* Multi-source Comparison Table */}
                      {item.sources && item.sources.length > 0 && (
                        <div className="mt-2 space-y-1.5">
                          <span className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                            <FileText className="w-3.5 h-3.5" />
                            {t('multiSourceMatrix')}
                          </span>
                          <div className="rounded-lg border overflow-hidden">
                            <table className="w-full text-left text-xs border-collapse">
                              <thead>
                                <tr className="bg-muted/50 border-b text-[11px] text-muted-foreground">
                                  <th className="p-2 font-medium">{t('sourceDoc')}</th>
                                  <th className="p-2 font-medium">{t('claimedValue')}</th>
                                  <th className="p-2 font-medium">{t('anchorTimestamp')}</th>
                                  <th className="p-2 font-medium">{t('contextSnippet')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {item.sources.map((src, sIdx) => (
                                  <tr
                                    key={sIdx}
                                    className="border-b last:border-b-0 hover:bg-muted/20 transition-colors"
                                  >
                                    <td className="p-2 font-medium text-foreground max-w-[160px] truncate">
                                      {src.document_title}
                                    </td>
                                    <td className="p-2 font-mono text-primary font-medium">{src.claimed_value}</td>
                                    <td className="p-2 font-mono text-muted-foreground text-[11px]">
                                      {src.line_anchor || src.timestamp_hint || '-'}
                                    </td>
                                    <td
                                      className="p-2 text-muted-foreground text-[11px] max-w-[240px] truncate"
                                      title={src.snippet}
                                    >
                                      {src.snippet || '-'}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {/* Affected Deliverables */}
                      {item.affected_artifacts && item.affected_artifacts.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          <span className="text-[11px] text-muted-foreground">{t('affectedDeliverables')}:</span>
                          {item.affected_artifacts.map((art, aIdx) => (
                            <span
                              key={aIdx}
                              className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground border"
                            >
                              {art}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

          {!loading && filteredItems.length === 0 && (
            <div className="py-16 text-center text-xs text-muted-foreground">{t('noItemsFound')}</div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default FactCheckSheetViewer;
