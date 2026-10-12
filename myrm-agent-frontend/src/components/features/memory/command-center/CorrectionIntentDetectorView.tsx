/**
 * [INPUT]
 * @/services/memory::(CorrectionSlotDTO, CorrectionIntentKindEnum)
 * Lucide icons (Search, Sparkles, Tag, CheckCircle2, AlertCircle)
 *
 * [OUTPUT]
 * Component: CorrectionIntentDetectorView
 *
 * [POS]
 * Interactive input and semantic slot extractor view for Item 128 Live Correction Studio.
 * Strictly typed, zero any, a11y compliant with visible focus rings and valid labels. Single file < 300 lines.
 */

'use client';

import React from 'react';
import { AlertCircle, CheckCircle2, Search, Sparkles, Tag } from 'lucide-react';
import type { CorrectionSlotDTO } from '@/services/memory';

interface CorrectionIntentDetectorViewProps {
  utterance: string;
  onUtteranceChange: (value: string) => void;
  onSubmit: () => void;
  isProcessing: boolean;
  sampleUtterances: string[];
  detectedSlot?: CorrectionSlotDTO | null;
}

const INTENT_LABELS: Record<string, { label: string; color: string }> = {
  preference_update: {
    label: '偏好更替 (Preference)',
    color: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
  },
  fact_superseded: {
    label: '事实更替 (Fact Superseded)',
    color: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20',
  },
  behavior_rule: {
    label: '行为规范 (Behavior Rule)',
    color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  },
  retract_mistake: {
    label: '撤回遗忘 (Retract Mistake)',
    color: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
  },
  general_amendment: {
    label: '通用修正 (Amendment)',
    color: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  },
};

export const CorrectionIntentDetectorView: React.FC<CorrectionIntentDetectorViewProps> = ({
  utterance,
  onUtteranceChange,
  onSubmit,
  isProcessing,
  sampleUtterances,
  detectedSlot,
}) => {
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (utterance.trim() && !isProcessing) {
      onSubmit();
    }
  };

  const intentMeta = detectedSlot?.intent
    ? INTENT_LABELS[detectedSlot.intent] || {
        label: detectedSlot.intent,
        color: 'bg-muted text-foreground border-border',
      }
    : null;

  return (
    <section
      aria-label="自然语言纠错指令输入与语义槽位分析"
      className="space-y-4 rounded-xl border border-border/80 bg-card/60 p-4 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-foreground">
            会话即时纠错指令 (Natural Language Input)
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">
          输入口语化纠正语句，引擎将自动提取新旧事实与更替意图
        </span>
      </div>

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label htmlFor="live-correction-utterance-input" className="sr-only">
            用户纠错指令
          </label>
          <div className="relative flex items-center">
            <input
              id="live-correction-utterance-input"
              type="text"
              value={utterance}
              onChange={(e) => onUtteranceChange(e.target.value)}
              placeholder="例如：我不喜欢美式咖啡，换成燕麦拿铁 / 其实主数据库是 SQLite..."
              className="w-full rounded-lg border border-input bg-background px-3 py-2.5 pr-28 text-sm text-foreground shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              disabled={isProcessing}
            />
            <button
              type="submit"
              disabled={!utterance.trim() || isProcessing}
              className="absolute right-1.5 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow transition hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 disabled:pointer-events-none disabled:opacity-50"
            >
              <Search className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{isProcessing ? '分析重校中...' : '即时重校'}</span>
            </button>
          </div>
        </div>

        {/* Quick Sample Chips */}
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
          <span className="font-medium">快捷预设测试:</span>
          {sampleUtterances.map((sample, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onUtteranceChange(sample)}
              disabled={isProcessing}
              className="rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs text-foreground transition hover:border-primary hover:bg-primary/5 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
            >
              {sample}
            </button>
          ))}
        </div>
      </form>

      {/* Extracted Semantic Slots Preview */}
      {detectedSlot && (
        <div className="mt-3 rounded-lg border border-border/60 bg-muted/30 p-3 text-xs">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5 font-medium text-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" aria-hidden="true" />
              <span>提取的语义槽位 (Extracted Semantic Slots)</span>
            </div>
            {intentMeta && (
              <span
                className={`inline-flex items-center rounded-md border px-2 py-0.5 font-semibold ${intentMeta.color}`}
              >
                {intentMeta.label}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-4">
            <div className="rounded border border-border/40 bg-background/50 p-2">
              <span className="block text-muted-foreground">新断言 / 目标值:</span>
              <span className="font-medium text-primary">
                {detectedSlot.corrected_value || '(无)'}
              </span>
            </div>
            <div className="rounded border border-border/40 bg-background/50 p-2">
              <span className="block text-muted-foreground">否定失效值:</span>
              <span className="font-medium text-rose-500 dark:text-rose-400">
                {detectedSlot.negated_value || '(无明确否定)'}
              </span>
            </div>
            <div className="rounded border border-border/40 bg-background/50 p-2">
              <span className="block text-muted-foreground">关联主体:</span>
              <span className="font-medium text-foreground">
                {detectedSlot.subject || '(全局会话上下文)'}
              </span>
            </div>
            <div className="rounded border border-border/40 bg-background/50 p-2">
              <span className="block text-muted-foreground">置信度:</span>
              <span className="font-medium text-emerald-600 dark:text-emerald-400">
                {(detectedSlot.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
