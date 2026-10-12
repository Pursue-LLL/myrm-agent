'use client';

/**
 * [INPUT]
 * - ./learningTimelineMeta::KIND_META, isSkill*, toImportanceScale (POS: 时间线节点展示元数据与状态读取)
 * - @/components/primitives/button::Button, @/components/primitives/card::Card (POS: 基础 UI 原语)
 * - @/services/statistics::LearningTimelineItem (POS: 学习时间线数据契约)
 *
 * [OUTPUT]
 * - TimelineNodeCard: 单个学习节点卡片，含行内编辑表单与来源对话入口；治理动作（保存/删除/归档）通过回调交给父级
 * - TimelineEditDraft: 行内编辑草稿
 *
 * [POS]
 * 学习时间线节点展示层。仅持有编辑草稿这一局部状态，不直接调用接口。
 */

import { memo, useId, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Archive, Check, ExternalLink, Edit3, Lock, MessageCircle, RotateCcw, Trash2, X } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import type { LearningTimelineItem } from '@/services/statistics';
import {
  KIND_META,
  isSkillArchived,
  isSkillManageable,
  isSkillNode,
  isSkillPinned,
  toImportanceScale,
} from './learningTimelineMeta';

export interface TimelineEditDraft {
  content: string;
  /** 1-10 scale shown to the user; the API takes 0-1. */
  importance: number;
  reasoning: string;
}

interface TimelineNodeCardProps {
  item: LearningTimelineItem;
  /** Display name of the originating agent; the raw id is never shown. */
  agentName?: string;
  onSaveEdit: (item: LearningTimelineItem, draft: TimelineEditDraft) => Promise<boolean>;
  onRequestDelete: (item: LearningTimelineItem) => void;
  onRequestSkillToggle: (item: LearningTimelineItem) => void;
  onSelectMemoryForGraph?: (memoryId: string) => void;
}

const FIELD_CLASS =
  'w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary';

export const TimelineNodeCard = memo<TimelineNodeCardProps>(
  ({ item, agentName, onSaveEdit, onRequestDelete, onRequestSkillToggle, onSelectMemoryForGraph }) => {
    const t = useTranslations('growthDashboard.learningTimeline');
    const fieldId = useId();
    const [editing, setEditing] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [draft, setDraft] = useState<TimelineEditDraft>({ content: '', importance: 5, reasoning: '' });

    const meta = KIND_META[item.kind] ?? KIND_META.fact_memory;
    const Icon = meta.icon;
    const isSkill = isSkillNode(item);
    const archived = isSkill && isSkillArchived(item);
    const pinned = isSkill && isSkillPinned(item);
    const isProcedural = item.kind === 'procedural_memory';
    // Procedural rules carry no importance score, so showing or editing one would be meaningless.
    const hasImportance = !isSkill && !isProcedural;
    const reasoning = typeof item.metadata?.reasoning === 'string' ? item.metadata.reasoning : '';
    const heading = isSkill || isProcedural ? item.title : '';
    const body = item.content || (isSkill ? t(`skillStatus.${item.status}`) : '');

    const startEdit = () => {
      setDraft({ content: item.content, importance: toImportanceScale(item.importance), reasoning });
      setEditing(true);
    };

    const save = async () => {
      setSubmitting(true);
      try {
        if (await onSaveEdit(item, draft)) {
          setEditing(false);
        }
      } finally {
        setSubmitting(false);
      }
    };

    return (
      <div className="relative group">
        <div
          className={cn(
            'absolute -left-6 top-3 flex h-5 w-5 items-center justify-center rounded-full border bg-background shadow-xs transition-transform group-hover:scale-110',
            meta.borderColor,
          )}
        >
          <Icon className={cn('h-2.5 w-2.5', meta.color)} />
        </div>

        <Card
          className={cn(
            'transition-all duration-200 hover:border-border/90 hover:shadow-xs',
            item.is_user_protected && 'border-violet-500/30 bg-violet-500/[0.02]',
            archived && 'opacity-60 border-dashed',
          )}
        >
          <CardContent className="p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
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

                {isSkill && (
                  <span className="rounded bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    {t(`skillStatus.${item.status}`)}
                  </span>
                )}

                {item.is_user_protected && (
                  <span className="inline-flex items-center gap-1 rounded-md border border-violet-500/30 bg-violet-500/10 px-1.5 py-0.5 text-[11px] font-medium text-violet-500">
                    <Lock className="h-2.5 w-2.5" />
                    {t('userProtectedBadge')}
                  </span>
                )}

                {agentName && (
                  <span className="rounded bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    {t('agentOrigin', { agent: agentName })}
                  </span>
                )}

                {hasImportance && item.importance > 0 && (
                  <span className="rounded bg-muted/60 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    {t('importanceValue', { value: toImportanceScale(item.importance) })}
                  </span>
                )}
              </div>

              <div className="flex items-center justify-between gap-1 sm:justify-end">
                <span className="text-[11px] text-muted-foreground/80 tabular-nums">
                  {new Date(item.created_at).toLocaleString()}
                </span>

                {!editing && (
                  <div className="flex items-center gap-0.5 opacity-80 transition-opacity group-hover:opacity-100">
                    {!isSkill ? (
                      <>
                        {item.source_chat_id && (
                          <Button
                            asChild
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                          >
                            <Link
                              href={`/${encodeURIComponent(item.source_chat_id)}`}
                              title={t('viewSourceChat')}
                              aria-label={t('viewSourceChat')}
                            >
                              <MessageCircle className="h-3.5 w-3.5" />
                            </Link>
                          </Button>
                        )}
                        {onSelectMemoryForGraph && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onSelectMemoryForGraph(item.id)}
                            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                            title={t('viewInGraph')}
                            aria-label={t('viewInGraph')}
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={startEdit}
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                          title={t('editMemory')}
                          aria-label={t('editMemory')}
                        >
                          <Edit3 className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => onRequestDelete(item)}
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          title={t('deleteMemory')}
                          aria-label={t('deleteMemory')}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </>
                    ) : (
                      isSkillManageable(item) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={pinned && !archived}
                          onClick={() => onRequestSkillToggle(item)}
                          className={cn(
                            'h-7 px-2 text-xs font-normal',
                            archived
                              ? 'text-emerald-500 hover:text-emerald-600'
                              : 'text-muted-foreground hover:text-amber-500',
                          )}
                          title={
                            pinned && !archived ? t('pinnedHint') : archived ? t('unarchiveSkill') : t('archiveSkill')
                          }
                        >
                          {archived ? (
                            <RotateCcw className="mr-1 h-3.5 w-3.5" />
                          ) : (
                            <Archive className="mr-1 h-3.5 w-3.5" />
                          )}
                          {archived ? t('unarchiveSkill') : t('archiveSkill')}
                        </Button>
                      )
                    )}
                  </div>
                )}
              </div>
            </div>

            {editing ? (
              <div className="mt-3 space-y-3 rounded-lg border border-border/80 bg-muted/20 p-3">
                <div className="space-y-1">
                  <label htmlFor={`${fieldId}-content`} className="text-xs font-medium text-foreground">
                    {t('contentLabel')}
                  </label>
                  <textarea
                    id={`${fieldId}-content`}
                    value={draft.content}
                    onChange={(e) => setDraft((prev) => ({ ...prev, content: e.target.value }))}
                    rows={3}
                    maxLength={2000}
                    className={FIELD_CLASS}
                  />
                </div>

                {isProcedural && (
                  <div className="space-y-1">
                    <label htmlFor={`${fieldId}-reasoning`} className="text-xs font-medium text-foreground">
                      {t('reasoningLabel')}
                    </label>
                    <textarea
                      id={`${fieldId}-reasoning`}
                      value={draft.reasoning}
                      onChange={(e) => setDraft((prev) => ({ ...prev, reasoning: e.target.value }))}
                      rows={2}
                      maxLength={2000}
                      className={FIELD_CLASS}
                    />
                  </div>
                )}

                <div
                  className={cn(
                    'flex flex-col gap-3 pt-1 sm:flex-row sm:items-center',
                    hasImportance ? 'sm:justify-between' : 'sm:justify-end',
                  )}
                >
                  {hasImportance && (
                    <div className="flex items-center gap-2">
                      <label htmlFor={`${fieldId}-importance`} className="text-xs text-muted-foreground">
                        {t('importanceLabel')}
                      </label>
                      <input
                        id={`${fieldId}-importance`}
                        type="range"
                        min={1}
                        max={10}
                        value={draft.importance}
                        onChange={(e) => setDraft((prev) => ({ ...prev, importance: Number(e.target.value) }))}
                        className="h-1.5 w-24 cursor-pointer accent-primary"
                      />
                      <span className="text-xs font-semibold text-foreground">{draft.importance}</span>
                    </div>
                  )}

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditing(false)}
                      disabled={submitting}
                      className="h-7 px-2.5 text-xs"
                    >
                      <X className="mr-1 h-3.5 w-3.5" />
                      {t('cancel')}
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      onClick={() => void save()}
                      disabled={submitting || !draft.content.trim()}
                      className="h-7 px-2.5 text-xs"
                    >
                      <Check className="mr-1 h-3.5 w-3.5" />
                      {t('saveChanges')}
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-2 space-y-1.5">
                {heading && <h4 className="text-sm font-semibold text-foreground">{heading}</h4>}
                {body && <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{body}</p>}
                {reasoning && (
                  <div className="mt-2 rounded-md border border-border/40 bg-muted/40 p-2 text-[11px] text-muted-foreground">
                    <span className="font-semibold text-foreground/80">{t('contextLabel')}: </span>
                    {reasoning}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    );
  },
);

TimelineNodeCard.displayName = 'TimelineNodeCard';
