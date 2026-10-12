/**
 * [INPUT]
 * @/services/memory/experienceObservability
 *
 * [OUTPUT]
 * ExperienceDistributionDashboardView: Triad view for experience items inventory,
 * source session traceability, and recall/injection effect distributions.
 *
 * [POS]
 * Sub-view of Item 108 ExperienceObservabilityStudioCard.
 * Strict typing applied, zero any, file length < 350 lines.
 */

import React, { useState } from 'react';
import {
  FileText,
  History,
  TrendingUp,
  ThumbsUp,
  ThumbsDown,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Sparkles,
  Layers,
  ChevronRight,
} from 'lucide-react';
import type {
  ExperienceObservabilityMetricDTO,
  SessionTraceEvidenceDTO,
} from '@/services/memory/experienceObservability';
import {
  fetchTraceEvidence,
  recordEffectOutcome,
} from '@/services/memory/experienceObservability';
import { FALLBACK_SESSION_TRACES } from './experienceObservabilityFallbacks';

interface ExperienceDistributionDashboardViewProps {
  metrics: ExperienceObservabilityMetricDTO[];
  onMetricUpdated: (updated: ExperienceObservabilityMetricDTO) => void;
}

export const ExperienceDistributionDashboardView: React.FC<
  ExperienceDistributionDashboardViewProps
> = ({ metrics, onMetricUpdated }) => {
  const [selectedEntryId, setSelectedEntryId] = useState<string>(
    metrics[0]?.entry_id || 'proc_git_push_safe',
  );
  const [traceEvidence, setTraceEvidence] =
    useState<SessionTraceEvidenceDTO | null>(
      FALLBACK_SESSION_TRACES.sess_release_incident_09 || null,
    );
  const [isLoadingTrace, setIsLoadingTrace] = useState(false);
  const [isSubmittingEffect, setIsSubmittingEffect] = useState(false);
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null);

  const selectedMetric =
    metrics.find((m) => m.entry_id === selectedEntryId) || metrics[0];

  const handleSelectEntry = async (entry: ExperienceObservabilityMetricDTO) => {
    setSelectedEntryId(entry.entry_id);
    setFeedbackNotice(null);
    setIsLoadingTrace(true);
    try {
      const trace = await fetchTraceEvidence(entry.source_session_id);
      setTraceEvidence(trace);
    } catch {
      // Local fallback
      const fallback =
        FALLBACK_SESSION_TRACES[entry.source_session_id] || {
          session_id: entry.source_session_id,
          title: `${entry.name} - 沉淀复盘会话`,
          trajectory_summary: '本地仿真会话：执行排障与重构提炼之原始证据轨迹。',
          key_evidence_snippets: [
            `[Evidence] 会话 ${entry.source_session_id} 提炼出本条经验核心规程。`,
          ],
          agent_role: 'AgentSpecialist',
          timestamp: new Date().toISOString(),
        };
      setTraceEvidence(fallback);
    } finally {
      setIsLoadingTrace(false);
    }
  };

  const handleReportEffect = async (isSuccess: boolean) => {
    if (!selectedMetric) return;
    setIsSubmittingEffect(true);
    setFeedbackNotice(null);
    try {
      const updated = await recordEffectOutcome(
        selectedMetric.entry_id,
        isSuccess,
        !isSuccess,
      );
      onMetricUpdated(updated);
      setFeedbackNotice(
        isSuccess
          ? `已记录任务成功归因（新有效率: ${Math.round(
              updated.success_rate * 100,
            )}%）`
          : `已记录争议反馈（新状态: ${updated.effect_status}）`,
      );
    } catch {
      // Offline fallback mutation
      const newSuccess = isSuccess
        ? selectedMetric.success_count + 1
        : selectedMetric.success_count;
      const newDispute = !isSuccess
        ? selectedMetric.dispute_count + 1
        : selectedMetric.dispute_count;
      const total = newSuccess + newDispute;
      const rate = total > 0 ? roundNumber(newSuccess / total) : 1.0;
      const status = rate >= 0.8 ? 'effective' : rate >= 0.5 ? 'neutral' : 'adverse';
      const localUpdated: ExperienceObservabilityMetricDTO = {
        ...selectedMetric,
        success_count: newSuccess,
        dispute_count: newDispute,
        success_rate: rate,
        effect_status: status,
        last_observed_at: new Date().toISOString(),
      };
      onMetricUpdated(localUpdated);
      setFeedbackNotice(
        isSuccess ? '（本地仿真）已记录任务采纳成功' : '（本地仿真）已记录用户纠偏争议',
      );
    } finally {
      setIsSubmittingEffect(false);
    }
  };

  const roundNumber = (num: number): number => Math.round(num * 1000) / 1000;

  return (
    <div className="space-y-4">
      {/* 2-Column Triad Layout: Left = Experience Inventory, Right = Session Trace & Effect */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left: Experience Inventory List (5 Cols) */}
        <div className="lg:col-span-5 p-3.5 bg-background rounded-lg border border-border/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-primary" />
              经验记忆全景列表 ({metrics.length})
            </span>
            <span className="text-[10px] text-muted-foreground font-mono">
              点击条目溯源证据
            </span>
          </div>

          <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
            {metrics.map((m) => {
              const isSelected = m.entry_id === selectedEntryId;
              const ratePercent = Math.round(m.success_rate * 100);
              return (
                <button
                  key={m.entry_id}
                  type="button"
                  onClick={() => handleSelectEntry(m)}
                  className={`w-full text-left p-2.5 rounded-lg border transition-all flex flex-col gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary ${
                    isSelected
                      ? 'bg-primary/5 border-primary/40 shadow-sm'
                      : 'bg-muted/20 border-border/40 hover:bg-muted/40 hover:border-border/70'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground truncate max-w-[200px]">
                      {m.name}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                        m.effect_status === 'effective'
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                          : m.effect_status === 'neutral'
                            ? 'bg-amber-500/10 text-amber-500'
                            : 'bg-destructive/10 text-destructive'
                      }`}
                    >
                      {m.effect_status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="font-mono">{m.entry_id}</span>
                    <span className="capitalize px-1.5 py-0.2 rounded bg-muted/60 text-[10px]">
                      {m.access_channel}
                    </span>
                  </div>

                  {/* Recall & Success Bar */}
                  <div className="flex items-center justify-between text-[10px] pt-1 border-t border-border/30 text-muted-foreground">
                    <span>
                      召回: {m.recall_count} | 注入: {m.injection_count}
                    </span>
                    <span className="font-semibold text-foreground">
                      成功率: {ratePercent}%
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Source Session Traceability & Effect Feedback (7 Cols) */}
        <div className="lg:col-span-7 space-y-3.5">
          {/* Top Panel: Source Session Traceability Card */}
          <div className="p-3.5 bg-background rounded-lg border border-border/60 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <History className="w-3.5 h-3.5 text-blue-500" />
                会话溯源证据链 (Session Traceability)
              </span>
              {selectedMetric && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground">
                  Session: {selectedMetric.source_session_id}
                </span>
              )}
            </div>

            {isLoadingTrace ? (
              <div className="py-8 text-center text-xs text-muted-foreground">
                正在加载来源 Session 证据链...
              </div>
            ) : traceEvidence ? (
              <div className="space-y-2 text-xs">
                <div className="p-2.5 bg-muted/20 rounded border border-border/40 space-y-1">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-primary" />
                    {traceEvidence.title}
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    {traceEvidence.trajectory_summary}
                  </p>
                </div>

                <div className="space-y-1.5">
                  <span className="text-[11px] font-mono text-muted-foreground block">
                    原始对话出处证据高亮:
                  </span>
                  <div className="space-y-1">
                    {traceEvidence.key_evidence_snippets.map((snip, idx) => (
                      <div
                        key={idx}
                        className="p-2 bg-muted/30 rounded border-l-2 border-primary text-[11px] font-mono text-foreground"
                      >
                        {snip}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-muted-foreground">
                未关联到原始会话证据
              </div>
            )}
          </div>

          {/* Bottom Panel: Effect Attribution & Feedback Simulator */}
          <div className="p-3.5 bg-background rounded-lg border border-border/60 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
                经验注入效果分布与反馈评估
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleReportEffect(true)}
                  disabled={isSubmittingEffect || !selectedMetric}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <ThumbsUp className="w-3 h-3" />
                  标记任务成功 ({selectedMetric?.success_count ?? 0})
                </button>
                <button
                  type="button"
                  onClick={() => handleReportEffect(false)}
                  disabled={isSubmittingEffect || !selectedMetric}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground rounded hover:bg-destructive/10 hover:text-destructive disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <ThumbsDown className="w-3 h-3" />
                  标记争议纠偏 ({selectedMetric?.dispute_count ?? 0})
                </button>
              </div>
            </div>

            {feedbackNotice && (
              <div className="text-xs p-2 bg-muted/40 rounded border border-border/50 text-foreground flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                {feedbackNotice}
              </div>
            )}

            {selectedMetric && (
              <div className="grid grid-cols-3 gap-2 pt-1 text-xs text-center">
                <div className="p-2 rounded bg-muted/20 border border-border/30">
                  <div className="text-[10px] text-muted-foreground">
                    召回 ➔ 注入转换率
                  </div>
                  <div className="text-sm font-semibold text-foreground font-mono">
                    {Math.round(
                      (selectedMetric.injection_count /
                        (selectedMetric.recall_count || 1)) *
                        100,
                    )}
                    %
                  </div>
                </div>

                <div className="p-2 rounded bg-muted/20 border border-border/30">
                  <div className="text-[10px] text-muted-foreground">
                    采纳成功率
                  </div>
                  <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400 font-mono">
                    {Math.round(selectedMetric.success_rate * 100)}%
                  </div>
                </div>

                <div className="p-2 rounded bg-muted/20 border border-border/30">
                  <div className="text-[10px] text-muted-foreground">
                    效果分类判定
                  </div>
                  <div className="text-sm font-semibold uppercase text-foreground font-mono">
                    {selectedMetric.effect_status}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
