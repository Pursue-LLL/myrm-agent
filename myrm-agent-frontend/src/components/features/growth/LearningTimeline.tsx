'use client';

/**
 * [INPUT]
 * - @/services/statistics::getLearningTimeline, updateTimelineMemory, deleteTimelineMemory, archiveTimelineSkill (POS: 学习时间线与治理数据接口)
 * - @/components/primitives/button::Button, @/components/primitives/card::Card (POS: 基础 UI 原语)
 *
 * [OUTPUT]
 * - LearningTimeline: 记忆与技能统一学习成长时间线面板，支持按类型过滤、时间跨度选择、就地行内编辑/删除/归档。
 *
 * [POS]
 * 成长与进化模块组件。在 /journey 页面提供直观的时序成长足迹展示与即时治理界面。
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Brain,
  Sparkles,
  Zap,
  BookOpen,
  Calendar,
  Layers,
  Edit3,
  Trash2,
  Archive,
  Lock,
  ChevronDown,
  ExternalLink,
  Check,
  X,
  AlertCircle,
  Clock,
  RotateCcw,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getLearningTimeline,
  updateTimelineMemory,
  deleteTimelineMemory,
  archiveTimelineSkill,
  type LearningTimelineItem,
  type TimelineNodeKind,
} from '@/services/statistics';
import { showApiError } from '@/lib/api';

const KIND_META: Record<
  TimelineNodeKind,
  {
    icon: typeof Brain;
    color: string;
    bgColor: string;
    borderColor: string;
    labelKey: string;
  }
> = {
  fact_memory: {
    icon: BookOpen,
    color: 'text-sky-500',
    bgColor: 'bg-sky-500/10',
    borderColor: 'border-sky-500/30',
    labelKey: 'filterFact',
  },
  preference_memory: {
    icon: Sparkles,
    color: 'text-violet-500',
    bgColor: 'bg-violet-500/10',
    borderColor: 'border-violet-500/30',
    labelKey: 'filterPreference',
  },
  procedural_memory: {
    icon: Layers,
    color: 'text-amber-500',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
    labelKey: 'filterProcedural',
  },
  episodic_memory: {
    icon: Calendar,
    color: 'text-emerald-500',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30',
    labelKey: 'filterEpisodic',
  },
  skill_evolution: {
    icon: Zap,
    color: 'text-cyan-500',
    bgColor: 'bg-cyan-500/10',
    borderColor: 'border-cyan-500/30',
    labelKey: 'filterEvolution',
  },
  skill_draft: {
    icon: Clock,
    color: 'text-rose-500',
    bgColor: 'bg-rose-500/10',
    borderColor: 'border-rose-500/30',
    labelKey: 'filterDraft',
  },
};

const FILTER_TABS: Array<{ id: string; labelKey: string }> = [
  { id: 'all', labelKey: 'filterAll' },
  { id: 'fact_memory', labelKey: 'filterFact' },
  { id: 'preference_memory', labelKey: 'filterPreference' },
  { id: 'procedural_memory', labelKey: 'filterProcedural' },
  { id: 'episodic_memory', labelKey: 'filterEpisodic' },
  { id: 'skill_evolution', labelKey: 'filterEvolution' },
  { id: 'skill_draft', labelKey: 'filterDraft' },
];

interface LearningTimelineProps {
  onSelectMemoryForGraph?: (memoryId: string) => void;
  className?: string;
}

export const LearningTimeline = memo<LearningTimelineProps>(({ onSelectMemoryForGraph, className }) => {
  const t = useTranslations('growthDashboard.learningTimeline');
  const [items, setItems] = useState<LearningTimelineItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedKind, setSelectedKind] = useState<string>('all');
  const [days, setDays] = useState<number>(30);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);

  // Edit modal / inline edit state
  const [editingItem, setEditingItem] = useState<LearningTimelineItem | null>(null);
  const [editContent, setEditContent] = useState<string>('');
  const [editImportance, setEditImportance] = useState<number>(5);
  const [editReasoning, setEditReasoning] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);

  const fetchTimeline = useCallback(
    async (reset = true) => {
      try {
        if (reset) {
          setLoading(true);
        } else {
          setLoadingMore(true);
        }
        const resp = await getLearningTimeline({
          days,
          kind_filter: selectedKind === 'all' ? undefined : selectedKind,
          limit: 20,
          cursor: reset ? undefined : nextCursor ?? undefined,
        });

        if (reset) {
          setItems(resp.items);
        } else {
          setItems((prev) => [...prev, ...resp.items]);
        }
        setTotalCount(resp.total_count);
        setHasMore(resp.has_more);
        setNextCursor(resp.next_cursor);
      } catch (err) {
        showApiError(err);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [days, selectedKind, nextCursor],
  );

  useEffect(() => {
    void fetchTimeline(true);
  }, [days, selectedKind]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleStartEdit = (item: LearningTimelineItem) => {
    setEditingItem(item);
    setEditContent(item.content);
    setEditImportance(Math.round(item.importance <= 1 ? item.importance * 10 : item.importance));
    setEditReasoning(typeof item.metadata?.reasoning === 'string' ? item.metadata.reasoning : '');
  };

  const handleCancelEdit = () => {
    setEditingItem(null);
    setEditContent('');
    setEditReasoning('');
  };

  const handleSaveEdit = async () => {
    if (!editingItem) {return;}
    try {
      setSubmitting(true);
      const memoryType = editingItem.kind.replace('_memory', '');
      await updateTimelineMemory(memoryType, editingItem.id, {
        content: editContent,
        importance: editImportance / 10,
        reasoning: editReasoning || undefined,
      });

      setItems((prev) =>
        prev.map((it) =>
          it.id === editingItem.id
            ? {
                ...it,
                content: editContent,
                importance: editImportance / 10,
                is_user_edited: true,
                metadata: { ...it.metadata, reasoning: editReasoning },
              }
            : it,
        ),
      );
      handleCancelEdit();
    } catch (err) {
      showApiError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteMemory = async (item: LearningTimelineItem) => {
    if (!window.confirm(t('deleteConfirm'))) {return;}
    try {
      const memoryType = item.kind.replace('_memory', '');
      await deleteTimelineMemory(item.id, memoryType);
      setItems((prev) => prev.filter((it) => it.id !== item.id));
      setTotalCount((prev) => Math.max(0, prev - 1));
    } catch (err) {
      showApiError(err);
    }
  };

  const handleToggleSkillArchive = async (item: LearningTimelineItem, active: boolean) => {
    const confirmMsg = active ? t('unarchiveConfirm') : t('archiveConfirm');
    if (!window.confirm(confirmMsg)) {return;}
    try {
      const skillId = (item.metadata?.skill_id as string) || item.id;
      await archiveTimelineSkill(skillId, active);
      setItems((prev) =>
        prev.map((it) =>
          it.id === item.id
            ? {
                ...it,
                status: active ? 'active' : 'archived',
                metadata: { ...it.metadata, is_active: active },
              }
            : it,
        ),
      );
    } catch (err) {
      showApiError(err);
    }
  };

  const userEditedCount = items.filter((i) => i.is_user_edited).length;

  return (
    <div className={cn('space-y-4', className)}>
      {/* Header filter controls */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          {FILTER_TABS.map((tab) => {
            const isSelected = selectedKind === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setSelectedKind(tab.id)}
                className={cn(
                  'rounded-lg px-2.5 py-1 text-xs font-medium transition-colors',
                  isSelected
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
              >
                {t(tab.labelKey)}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="hidden md:inline-block font-mono">
            {t('stats.totalNodes', { count: totalCount })}
          </span>
          {userEditedCount > 0 && (
            <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[11px] font-medium text-violet-500 border border-violet-500/20">
              {t('stats.userEditedCount', { count: userEditedCount })}
            </span>
          )}
          <div className="flex rounded-md border border-border/60 bg-muted/40 p-0.5">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDays(d)}
                className={cn(
                  'rounded px-2 py-0.5 text-xs transition-colors',
                  days === d ? 'bg-background font-medium text-foreground shadow-xs' : 'text-muted-foreground',
                )}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex min-h-[300px] items-center justify-center rounded-xl border border-dashed border-border/60">
          <div className="flex flex-col items-center gap-2">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span className="text-xs text-muted-foreground">{t('loading')}</span>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && items.length === 0 && (
        <div className="flex min-h-[300px] flex-col items-center justify-center rounded-xl border border-dashed border-border/70 p-8 text-center">
          <div className="rounded-full bg-muted p-3">
            <Brain className="h-6 w-6 text-muted-foreground" />
          </div>
          <h3 className="mt-3 text-sm font-semibold text-foreground">{t('empty.title')}</h3>
          <p className="mt-1 max-w-sm text-xs text-muted-foreground">{t('empty.description')}</p>
        </div>
      )}

      {/* Timeline Stream */}
      {!loading && items.length > 0 && (
        <div className="relative pl-6 space-y-4 before:absolute before:bottom-2 before:left-2.5 before:top-2 before:w-[2px] before:bg-border/60">
          {items.map((item) => {
            const meta = KIND_META[item.kind] ?? KIND_META.fact_memory;
            const Icon = meta.icon;
            const isEditing = editingItem?.id === item.id;
            const isSkill = item.kind === 'skill_evolution' || item.kind === 'skill_draft';
            const isArchived = item.status === 'archived' || item.metadata?.is_active === false;

            return (
              <div key={item.id} className="relative group">
                {/* Node marker point */}
                <div
                  className={cn(
                    'absolute -left-6 top-3 flex h-5 w-5 items-center justify-center rounded-full border bg-background shadow-xs transition-transform group-hover:scale-110',
                    meta.borderColor,
                  )}
                >
                  <Icon className={cn('h-2.5 w-2.5', meta.color)} />
                </div>

                {/* Node Card */}
                <Card
                  className={cn(
                    'transition-all duration-200 hover:border-border/90 hover:shadow-xs',
                    item.is_user_edited && 'border-violet-500/30 bg-violet-500/[0.02]',
                    isArchived && 'opacity-60 border-dashed',
                  )}
                >
                  <CardContent className="p-4">
                    {/* Top Row: Meta Badge & Controls */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={cn(
                            'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium',
                            meta.bgColor,
                            meta.color,
                          )}
                        >
                          <Icon className="h-3 w-3" />
                          {t(meta.labelKey)}
                        </span>

                        {item.is_user_edited && (
                          <span className="inline-flex items-center gap-1 rounded-md border border-violet-500/30 bg-violet-500/10 px-1.5 py-0.5 text-[11px] font-medium text-violet-500">
                            <Lock className="h-2.5 w-2.5" />
                            {t('userLockedBadge')}
                          </span>
                        )}

                        {item.agent_id && (
                          <span className="rounded bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground font-mono">
                            {t('agentOrigin', { agent: item.agent_id })}
                          </span>
                        )}

                        {item.importance > 0 && (
                          <span className="rounded bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                            ★ {item.importance}/10
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-muted-foreground/80 font-mono">
                          {new Date(item.created_at).toLocaleString()}
                        </span>

                        {/* Inline Governance Action Buttons */}
                        {!isEditing && (
                          <div className="flex items-center gap-0.5 opacity-80 group-hover:opacity-100 transition-opacity">
                            {!isSkill ? (
                              <>
                                {onSelectMemoryForGraph && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => onSelectMemoryForGraph(item.id)}
                                    className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                                    title="View in Knowledge Graph"
                                  >
                                    <ExternalLink className="h-3.5 w-3.5" />
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleStartEdit(item)}
                                  className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                                  title={t('editMemory')}
                                >
                                  <Edit3 className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleDeleteMemory(item)}
                                  className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                                  title={t('deleteMemory')}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </>
                            ) : (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleToggleSkillArchive(item, isArchived)}
                                className={cn(
                                  'h-7 px-2 text-xs font-normal',
                                  isArchived
                                    ? 'text-emerald-500 hover:text-emerald-600'
                                    : 'text-muted-foreground hover:text-amber-500',
                                )}
                                title={isArchived ? t('unarchiveSkill') : t('archiveSkill')}
                              >
                                {isArchived ? (
                                  <RotateCcw className="h-3.5 w-3.5 mr-1" />
                                ) : (
                                  <Archive className="h-3.5 w-3.5 mr-1" />
                                )}
                                {isArchived ? t('unarchiveSkill') : t('archiveSkill')}
                              </Button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Content Section: View Mode vs Edit Mode */}
                    {isEditing ? (
                      <div className="mt-3 space-y-3 rounded-lg border border-border/80 bg-muted/20 p-3">
                        <div className="space-y-1">
                          <label className="text-xs font-medium text-foreground">{t('contentLabel')}</label>
                          <textarea
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            rows={3}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                          />
                        </div>

                        <div className="space-y-1">
                          <label className="text-xs font-medium text-foreground">{t('reasoningLabel')}</label>
                          <textarea
                            value={editReasoning}
                            onChange={(e) => setEditReasoning(e.target.value)}
                            rows={2}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                          />
                        </div>

                        <div className="flex items-center justify-between pt-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">{t('importanceLabel')}</span>
                            <input
                              type="range"
                              min={1}
                              max={10}
                              value={editImportance}
                              onChange={(e) => setEditImportance(Number(e.target.value))}
                              className="h-1.5 w-24 cursor-pointer accent-primary"
                            />
                            <span className="text-xs font-semibold text-foreground">{editImportance}</span>
                          </div>

                          <div className="flex items-center gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={handleCancelEdit}
                              disabled={submitting}
                              className="h-7 px-2.5 text-xs"
                            >
                              <X className="h-3.5 w-3.5 mr-1" />
                              {t('cancel')}
                            </Button>
                            <Button
                              variant="default"
                              size="sm"
                              onClick={handleSaveEdit}
                              disabled={submitting || !editContent.trim()}
                              className="h-7 px-2.5 text-xs"
                            >
                              <Check className="h-3.5 w-3.5 mr-1" />
                              {t('saveChanges')}
                            </Button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-2 space-y-1.5">
                        <h4 className="text-sm font-semibold text-foreground">{item.title}</h4>
                        <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
                          {item.content}
                        </p>

                        {/* Extra metadata fields */}
                        {typeof item.metadata?.reasoning === 'string' && item.metadata.reasoning.length > 0 && (
                          <div className="mt-2 rounded-md bg-muted/40 p-2 text-[11px] text-muted-foreground border border-border/40">
                            <span className="font-semibold text-foreground/80">Context: </span>
                            {item.metadata.reasoning}
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            );
          })}

          {/* Load More Button */}
          {hasMore && (
            <div className="pt-2 text-center">
              <Button
                variant="outline"
                size="sm"
                onClick={() => fetchTimeline(false)}
                disabled={loadingMore}
                className="text-xs"
              >
                {loadingMore ? (
                  <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary border-t-transparent mr-2" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5 mr-1" />
                )}
                {t('loadMore')}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

LearningTimeline.displayName = 'LearningTimeline';

export default LearningTimeline;
