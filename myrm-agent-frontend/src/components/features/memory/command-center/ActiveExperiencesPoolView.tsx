/**
 * Active Experiences Pool and Reinforcement Console View.
 * Displays active memory fragments with bounded logarithmic compounding weight tracking,
 * hit/adoption telemetry, active lease protection badges, and inline reinforcement controls.
 */

import React, { useState } from 'react';
import { Layers, Plus, ThumbsUp, ThumbsDown, Pin, Clock, Tag } from 'lucide-react';
import {
  AddExperienceItemRequest,
  CompoundedExperienceItemDTO,
} from '@/services/memory/experienceCompounding';

interface ActiveExperiencesPoolViewProps {
  experiences: CompoundedExperienceItemDTO[];
  onReinforce: (itemId: string) => Promise<void>;
  onPenalize: (itemId: string) => Promise<void>;
  onAddExperience: (req: AddExperienceItemRequest) => Promise<void>;
  isProcessing: boolean;
}

export const ActiveExperiencesPoolView: React.FC<ActiveExperiencesPoolViewProps> = ({
  experiences,
  onReinforce,
  onPenalize,
  onAddExperience,
  isProcessing,
}) => {
  const [isAdding, setIsAdding] = useState(false);
  const [content, setContent] = useState('');
  const [topic, setTopic] = useState('coding_style');
  const [isPinned, setIsPinned] = useState(false);
  const [isTemporary, setIsTemporary] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim() || !topic.trim()) return;

    await onAddExperience({
      content: content.trim(),
      topic: topic.trim(),
      is_pinned: isPinned,
      is_temporary: isTemporary,
      tags: [topic.trim(), ...(isPinned ? ['pinned'] : []), ...(isTemporary ? ['temporary'] : [])],
    });

    setContent('');
    setIsAdding(false);
  };

  return (
    <section className="bg-card/70 border border-border/70 rounded-xl p-4 shadow-xs space-y-3.5">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-500">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">活跃热经验池</h3>
            <p className="text-xs text-muted-foreground">
              参与日常对话召回的热碎片，验证采纳时自动有界对数加固，延长半衰期
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsAdding(!isAdding)}
          className="text-xs px-2.5 py-1.5 rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors flex items-center gap-1 focus:outline-hidden focus:ring-2 focus:ring-primary font-medium"
        >
          <Plus className="w-3.5 h-3.5" />
          {isAdding ? '收起表单' : '录入新经验'}
        </button>
      </header>

      {/* Add New Experience Drawer Form */}
      {isAdding && (
        <form
          onSubmit={handleSubmit}
          className="p-3.5 rounded-xl bg-muted/40 border border-border/60 space-y-2.5 transition-all text-xs"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <div>
              <label htmlFor="exp-topic-input" className="block text-xs font-medium text-foreground mb-1">
                领域主题 (Topic)
              </label>
              <input
                id="exp-topic-input"
                type="text"
                required
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="例如: frontend, quality, workflow"
                className="w-full text-xs px-3 py-1.5 rounded-lg bg-background border border-input focus:outline-hidden focus:ring-2 focus:ring-primary text-foreground"
              />
            </div>

            <div className="flex items-center gap-4 pt-4 sm:pt-5">
              <label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground hover:text-foreground">
                <input
                  type="checkbox"
                  checked={isPinned}
                  onChange={(e) => setIsPinned(e.target.checked)}
                  className="rounded border-input text-primary focus:ring-primary"
                />
                <Pin className="w-3 h-3 text-amber-500" />
                <span>核心常驻 (豁免退火)</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground hover:text-foreground">
                <input
                  type="checkbox"
                  checked={isTemporary}
                  onChange={(e) => setIsTemporary(e.target.checked)}
                  className="rounded border-input text-primary focus:ring-primary"
                />
                <Clock className="w-3 h-3 text-sky-500" />
                <span>临时上下文 (3天衰减)</span>
              </label>
            </div>
          </div>

          <div>
            <label htmlFor="exp-content-input" className="block text-xs font-medium text-foreground mb-1">
              经验或偏好细节陈述
            </label>
            <textarea
              id="exp-content-input"
              required
              rows={2}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="输入如：Python 代码严禁使用 Any 类型，需使用具体的 Type Hints..."
              className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-input focus:outline-hidden focus:ring-2 focus:ring-primary text-foreground"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setIsAdding(false)}
              className="px-3 py-1 text-xs rounded-lg border border-border bg-background hover:bg-muted text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isProcessing}
              className="px-3.5 py-1 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-hidden focus:ring-2 focus:ring-primary disabled:opacity-50"
            >
              提交保存
            </button>
          </div>
        </form>
      )}

      {/* Experience List */}
      <div className="space-y-2.5">
        {experiences.map((item) => (
          <article
            key={item.item_id}
            className="p-3 rounded-xl bg-background/70 border border-border/50 hover:border-border transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-2.5"
          >
            <div className="space-y-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-secondary text-secondary-foreground border border-border/40">
                  {item.topic}
                </span>
                {item.is_pinned && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 font-semibold flex items-center gap-0.5">
                    <Pin className="w-2.5 h-2.5" /> 核心常驻
                  </span>
                )}
                {item.is_temporary && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-sky-500/10 text-sky-600 dark:text-sky-400 font-semibold flex items-center gap-0.5">
                    <Clock className="w-2.5 h-2.5" /> 一次性临时
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground font-mono">
                  半衰期: {item.half_life_days.toFixed(0)}天
                </span>
              </div>
              <p className="text-xs text-foreground font-medium leading-relaxed">
                {item.content}
              </p>
              {item.tags.length > 0 && (
                <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Tag className="w-2.5 h-2.5" />
                  <span>{item.tags.join(', ')}</span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-auto">
              <div className="text-right">
                <span className="text-[10px] text-muted-foreground block">当前权重</span>
                <output aria-live="polite" className="text-xs font-bold text-primary font-mono block">
                  {item.compounded_weight.toFixed(2)}x
                </output>
                <span className="text-[10px] text-muted-foreground block">
                  采纳 {item.adoption_count} / 命 {item.hit_count}
                </span>
              </div>
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => onReinforce(item.item_id)}
                className="px-2 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600/15 hover:bg-emerald-600/25 text-emerald-600 dark:text-emerald-400 transition-colors flex items-center gap-1 focus:outline-hidden focus:ring-2 focus:ring-primary disabled:opacity-50"
              >
                <ThumbsUp className="w-3 h-3" />
                采纳加固
              </button>
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => onPenalize(item.item_id)}
                aria-label={`纠偏降权经验 [${item.item_id}]`}
                className="px-2 py-1.5 text-xs font-semibold rounded-lg bg-rose-600/15 hover:bg-rose-600/25 text-rose-600 dark:text-rose-400 transition-colors flex items-center gap-1 focus:outline-hidden focus:ring-2 focus:ring-primary disabled:opacity-50"
              >
                <ThumbsDown className="w-3 h-3" />
                纠偏降权
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
};
