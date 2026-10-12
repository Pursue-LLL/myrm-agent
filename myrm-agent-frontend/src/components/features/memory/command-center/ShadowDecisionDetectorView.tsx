/**
 * Shadow Decision Intent Detector and Simulation View.
 * Enables live sniffing of architectural commitments, distinguishing exploratory questions from high-stakes decisions.
 */

import React, { useState } from 'react';
import { Eye, Sparkles, Search, CheckCircle2, AlertCircle } from 'lucide-react';
import { mockPredefinedQueries } from './decisionAssistFallbacks';
import { PitfallEvaluationResponse } from '@/services/memory/decisionAssist';

interface ShadowDecisionDetectorViewProps {
  onEvaluate: (query: string) => Promise<void>;
  isEvaluating: boolean;
  evaluationResult: PitfallEvaluationResponse | null;
}

export const ShadowDecisionDetectorView: React.FC<ShadowDecisionDetectorViewProps> = ({
  onEvaluate,
  isEvaluating,
  evaluationResult,
}) => {
  const [inputText, setInputText] = useState(mockPredefinedQueries[0].query);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputText.trim()) {
      onEvaluate(inputText.trim());
    }
  };

  return (
    <section className="bg-card/70 border border-border/70 rounded-xl p-4 shadow-xs space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Eye className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">影子决策意图嗅探器</h3>
            <p className="text-xs text-muted-foreground">
              亚毫秒状态机预检，严格区分探讨咨询（静默放行）与实质技术选型（触发因果反查）
            </p>
          </div>
        </div>
        <span className="text-xs px-2.5 py-1 rounded-full font-medium bg-secondary text-secondary-foreground border border-border/50">
          极速正则状态机
        </span>
      </div>

      {/* Preset Quick Test Cases */}
      <div className="space-y-1.5">
        <div className="text-xs font-medium text-muted-foreground">预设场景快速演练:</div>
        <div className="flex flex-wrap gap-2">
          {mockPredefinedQueries.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                setInputText(item.query);
                onEvaluate(item.query);
              }}
              className="text-xs px-2.5 py-1.5 rounded-lg bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors border border-border/40 focus:outline-hidden focus:ring-2 focus:ring-primary"
            >
              <Sparkles className="w-3 h-3 inline-block mr-1 text-primary/80" />
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Input Form with proper htmlFor label and focus ring */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label htmlFor="decision-sniff-input" className="block text-xs font-medium text-foreground mb-1.5">
            拟定技术方案或架构决策陈述
          </label>
          <div className="relative">
            <input
              id="decision-sniff-input"
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="输入如：我们决定换成 redis 作为分布式锁方案..."
              className="w-full text-sm px-3.5 py-2.5 rounded-lg bg-background border border-input focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-primary transition-all text-foreground"
            />
          </div>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            响应特性: 嗅探耗时 &lt; 0.5ms，纯本地执行，零额外 LLM 延迟
          </span>
          <button
            type="submit"
            disabled={isEvaluating || !inputText.trim()}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-all flex items-center gap-1.5 focus:outline-hidden focus:ring-2 focus:ring-primary shadow-xs"
          >
            <Search className="w-3.5 h-3.5" />
            {isEvaluating ? '实时嗅探中...' : '立即嗅探意图'}
          </button>
        </div>
      </form>

      {/* Evaluation Telemetry Output */}
      {evaluationResult && (
        <article className="pt-2 border-t border-border/50">
          <div className="text-xs font-medium text-muted-foreground mb-2">嗅探评估结果:</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
            <div className="p-2 rounded-lg bg-muted/30 border border-border/40">
              <span className="text-muted-foreground block text-[11px]">意图捕捉</span>
              <output aria-live="polite" className="font-semibold text-foreground flex items-center gap-1 mt-0.5">
                {evaluationResult.intent_detected ? (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> 已识别
                  </>
                ) : (
                  <>
                    <AlertCircle className="w-3.5 h-3.5 text-muted-foreground" /> 未捕获
                  </>
                )}
              </output>
            </div>

            <div className="p-2 rounded-lg bg-muted/30 border border-border/40">
              <span className="text-muted-foreground block text-[11px]">决策级别</span>
              <output aria-live="polite" className="font-semibold text-foreground block mt-0.5">
                {evaluationResult.intent_level === 'commitment' ? (
                  <span className="text-amber-500 font-bold">实质选型 (Commitment)</span>
                ) : evaluationResult.intent_level === 'inquiry' ? (
                  <span className="text-sky-500">探讨咨询 (Inquiry)</span>
                ) : (
                  '无'
                )}
              </output>
            </div>

            <div className="p-2 rounded-lg bg-muted/30 border border-border/40">
              <span className="text-muted-foreground block text-[11px]">教训匹配</span>
              <output aria-live="polite" className="font-semibold text-foreground block mt-0.5">
                {evaluationResult.triad_matched ? (
                  <span className="text-rose-500 font-bold">命中历史踩坑</span>
                ) : (
                  <span className="text-emerald-500">无负面踩坑</span>
                )}
              </output>
            </div>

            <div className="p-2 rounded-lg bg-muted/30 border border-border/40">
              <span className="text-muted-foreground block text-[11px]">嗅探耗时</span>
              <output aria-live="polite" className="font-semibold text-foreground block mt-0.5 font-mono">
                {evaluationResult.latency_ms.toFixed(2)} ms
              </output>
            </div>
          </div>
        </article>
      )}
    </section>
  );
};
