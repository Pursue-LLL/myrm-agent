/**
 * [INPUT]
 * - @/services/statistics::LearningTimelineItem, TimelineNodeKind (POS: 学习时间线数据契约)
 *
 * [OUTPUT]
 * - KIND_META / FILTER_TABS: 节点类型的图标、配色与文案键
 * - isSkillNode / isSkillArchived / isSkillPinned / isSkillManageable: 技能节点状态读取（服务端元数据为唯一事实源）
 * - memoryTypeOf: 记忆节点的变更类型（直接取服务端 metadata.memory_type，不在前端推导）
 * - RECOVERABLE_MEMORY_TYPES: 可软删除（可撤销）的记忆类型
 * - toImportanceScale: 服务端 0-1 重要度与界面 1-10 刻度的换算
 * - compareTimelineItems: 与服务端一致的 (created_at, id) 倒序比较
 *
 * [POS]
 * 学习时间线的纯展示元数据与节点状态读取，供 LearningTimeline 与 TimelineNodeCard 共享。
 */

import { BookOpen, Calendar, Clock, Layers, Sparkles, Zap, type LucideIcon } from 'lucide-react';
import type { LearningTimelineItem, TimelineNodeKind } from '@/services/statistics';

export interface KindMeta {
  icon: LucideIcon;
  color: string;
  bgColor: string;
  borderColor: string;
  labelKey: string;
}

export const KIND_META: Record<TimelineNodeKind, KindMeta> = {
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

export const FILTER_TABS: ReadonlyArray<{ id: string; labelKey: string }> = [
  { id: 'all', labelKey: 'filterAll' },
  { id: 'fact_memory', labelKey: 'filterFact' },
  { id: 'preference_memory', labelKey: 'filterPreference' },
  { id: 'procedural_memory', labelKey: 'filterProcedural' },
  { id: 'episodic_memory', labelKey: 'filterEpisodic' },
  { id: 'skill_evolution', labelKey: 'filterEvolution' },
  { id: 'skill_draft', labelKey: 'filterDraft' },
];

/** Memory types the server archives instead of purging, so their deletion can be undone. */
export const RECOVERABLE_MEMORY_TYPES: ReadonlySet<string> = new Set(['semantic', 'episodic']);

export const isSkillNode = (item: LearningTimelineItem): boolean =>
  item.kind === 'skill_evolution' || item.kind === 'skill_draft';

export const skillNameOf = (item: LearningTimelineItem): string =>
  typeof item.metadata?.skill_name === 'string' ? item.metadata.skill_name : '';

export const isSkillManageable = (item: LearningTimelineItem): boolean =>
  isSkillNode(item) && item.metadata?.manageable === true && skillNameOf(item) !== '';

export const isSkillArchived = (item: LearningTimelineItem): boolean => item.metadata?.archived === true;

export const isSkillPinned = (item: LearningTimelineItem): boolean => item.metadata?.pinned === true;

export const memoryTypeOf = (item: LearningTimelineItem): string =>
  typeof item.metadata?.memory_type === 'string' ? item.metadata.memory_type : '';

/** The API stores importance as 0-1; the UI edits it on a 1-10 scale. */
export const toImportanceScale = (importance: number): number => Math.min(10, Math.max(1, Math.round(importance * 10)));

/** Newest first; id breaks ties exactly like the server cursor ordering. */
export const compareTimelineItems = (a: LearningTimelineItem, b: LearningTimelineItem): number => {
  const diff = Date.parse(b.created_at) - Date.parse(a.created_at);
  if (diff !== 0) {
    return diff;
  }
  return a.id < b.id ? 1 : a.id > b.id ? -1 : 0;
};
