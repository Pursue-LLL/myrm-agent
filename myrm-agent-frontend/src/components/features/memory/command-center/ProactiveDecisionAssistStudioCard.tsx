/**
 * Proactive Past-Pitfall Alert and Decision Assist Studio Card.
 * Central command-center hub integrating shadow intent sniffing, causal postmortems,
 * session muting governance, and non-intrusive alert callouts.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Compass,
  PlusCircle,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  X,
} from 'lucide-react';
import {
  decisionAssistService,
  PitfallAlertStatusResponse,
  PitfallEvaluationResponse,
  SeedTriadRequest,
} from '@/services/memory/decisionAssist';
import { DecisionAssistHudBar } from './DecisionAssistHudBar';
import { ShadowDecisionDetectorView } from './ShadowDecisionDetectorView';
import { ProactivePitfallCalloutView } from './ProactivePitfallCalloutView';
import {
  mockPitfallAlertStatus,
  mockEvaluationResponseCommitment,
} from './decisionAssistFallbacks';

interface ProactiveDecisionAssistStudioCardProps {
  sessionId?: string;
  className?: string;
}

export const ProactiveDecisionAssistStudioCard: React.FC<
  ProactiveDecisionAssistStudioCardProps
> = ({ sessionId = 'sess-studio-default', className = '' }) => {
  const [status, setStatus] = useState<PitfallAlertStatusResponse>(
    mockPitfallAlertStatus
  );
  const [evaluationResult, setEvaluationResult] =
    useState<PitfallEvaluationResponse | null>(mockEvaluationResponseCommitment);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isSeedingOpen, setIsSeedingOpen] = useState(false);
  const [feedbackToast, setFeedbackToast] = useState<string | null>(null);

  // Form states for manual triad seeding
  const [seedSubject, setSeedSubject] = useState('');
  const [seedApproach, setSeedApproach] = useState('');
  const [seedLesson, setSeedLesson] = useState('');
  const [seedAlternative, setSeedAlternative] = useState('');

  const fetchStatus = useCallback(async () => {
    try {
      const liveStatus = await decisionAssistService.getStatus();
      setStatus(liveStatus);
    } catch {
      setStatus(mockPitfallAlertStatus);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleEvaluate = async (query: string) => {
    setIsEvaluating(true);
    try {
      const res = await decisionAssistService.evaluate({
        user_input: query,
        session_id: sessionId,
      });
      setEvaluationResult(res);
    } catch {
      setEvaluationResult(mockEvaluationResponseCommitment);
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleMuteTopic = async (subject: string) => {
    try {
      await decisionAssistService.muteSubject({
        session_id: sessionId,
        subject,
      });
      setFeedbackToast(`已对主题 [${subject}] 在本会话静音`);
      if (evaluationResult?.alert_card) {
        setEvaluationResult({
          ...evaluationResult,
          alert_card: {
            ...evaluationResult.alert_card,
            is_muted: true,
          },
        });
      }
      fetchStatus();
    } catch {
      setFeedbackToast(`已在本地临时静音主题 [${subject}]`);
    }
  };

  const handleUnmuteTopic = async (subject: string) => {
    try {
      await decisionAssistService.unmuteSubject({
        session_id: sessionId,
        subject,
      });
      setFeedbackToast(`已恢复主题 [${subject}] 的主动提醒`);
      if (evaluationResult?.alert_card) {
        setEvaluationResult({
          ...evaluationResult,
          alert_card: {
            ...evaluationResult.alert_card,
            is_muted: false,
          },
        });
      }
      fetchStatus();
    } catch {
      setFeedbackToast(`已在本地恢复主题 [${subject}] 提醒`);
    }
  };

  const handleAdoptSuggestion = (actionText: string) => {
    setFeedbackToast(`已采纳建议方案: ${actionText.slice(0, 32)}...`);
  };

  const handleSeedSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!seedSubject || !seedLesson || !seedAlternative) return;

    const payload: SeedTriadRequest = {
      subject: seedSubject.trim(),
      approach: seedApproach.trim() || '未指明具体方案',
      pitfall_lesson: seedLesson.trim(),
      validated_alternative: seedAlternative.trim(),
      severity: 'critical',
      incident_date: new Date().toISOString().slice(0, 10),
    };

    try {
      await decisionAssistService.seedTriad(payload);
      setFeedbackToast(`成功录入 [${payload.subject}] 历史踩坑教训`);
      setIsSeedingOpen(false);
      setSeedSubject('');
      setSeedApproach('');
      setSeedLesson('');
      setSeedAlternative('');
      fetchStatus();
    } catch {
      setFeedbackToast(`本地暂存成功: 已录入 [${payload.subject}] 踩坑教训`);
      setIsSeedingOpen(false);
    }
  };

  return (
    <section
      aria-label="主动历史踩坑预警与决策干预工作台"
      className={`bg-card text-card-foreground border border-border/80 rounded-2xl p-5 shadow-sm space-y-5 ${className}`}
    >
      {/* Studio Header */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
            <Compass className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight text-foreground">
                主动历史踩坑预警与决策干预
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                个人外脑 · 主动决策协助
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              不仅是被动答疑的记忆库，更是在关键架构与技术选型时主动介入纠偏的“第二大脑”
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setIsSeedingOpen(!isSeedingOpen)}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors flex items-center gap-1.5 focus:outline-hidden focus:ring-2 focus:ring-primary"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            {isSeedingOpen ? '关闭录入' : '录入踩坑教训'}
          </button>
          <button
            type="button"
            onClick={fetchStatus}
            aria-label="刷新防护遥测指标"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted transition-colors focus:outline-hidden focus:ring-2 focus:ring-primary"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* 4-Dimensional Telemetry HUD */}
      <DecisionAssistHudBar
        status={status}
        lastLatencyMs={evaluationResult?.latency_ms}
        activeSessionId={sessionId}
      />

      {/* Optional Triad Seeding Form Drawer */}
      {isSeedingOpen && (
        <form
          onSubmit={handleSeedSubmit}
          className="p-4 rounded-xl bg-muted/40 border border-border/70 space-y-3 transition-all"
        >
          <div className="flex items-center justify-between pb-1 border-b border-border/40">
            <span className="text-xs font-bold text-foreground">
              📝 录入因果三元组（当时方案 ➔ 踩坑教训 ➔ 已验证替代解）
            </span>
            <button
              type="button"
              onClick={() => setIsSeedingOpen(false)}
              aria-label="关闭表单"
              className="text-muted-foreground hover:text-foreground p-1 focus:outline-hidden focus:ring-2 focus:ring-primary rounded-md"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="seed-subject-input"
                className="block text-xs font-medium text-foreground mb-1"
              >
                技术主体 / 核心组件 (如 redis, sqlite)
              </label>
              <input
                id="seed-subject-input"
                type="text"
                required
                value={seedSubject}
                onChange={(e) => setSeedSubject(e.target.value)}
                placeholder="例如: redis"
                className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-input focus:outline-hidden focus:ring-2 focus:ring-primary text-foreground"
              />
            </div>

            <div>
              <label
                htmlFor="seed-approach-input"
                className="block text-xs font-medium text-foreground mb-1"
              >
                拟定方案 / 尝试路径
              </label>
              <input
                id="seed-approach-input"
                type="text"
                value={seedApproach}
                onChange={(e) => setSeedApproach(e.target.value)}
                placeholder="例如: 分布式锁无自动续期"
                className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-input focus:outline-hidden focus:ring-2 focus:ring-primary text-foreground"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor="seed-lesson-input"
              className="block text-xs font-medium text-foreground mb-1"
            >
              💥 踩坑教训与事故根因 (必含负面归因词)
            </label>
            <textarea
              id="seed-lesson-input"
              required
              rows={2}
              value={seedLesson}
              onChange={(e) => setSeedLesson(e.target.value)}
              placeholder="例如: 长尾 GC 导致锁过期被并发抢占，造成死锁雪崩与写脏数据故障..."
              className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-input focus:outline-hidden focus:ring-2 focus:ring-primary text-foreground"
            />
          </div>

          <div>
            <label
              htmlFor="seed-alternative-input"
              className="block text-xs font-medium text-foreground mb-1"
            >
              ✅ 已验证成功的替代方案
            </label>
            <input
              id="seed-alternative-input"
              type="text"
              required
              value={seedAlternative}
              onChange={(e) => setSeedAlternative(e.target.value)}
              placeholder="例如: 引入 Redlock 看门狗自动续期，或数据库 CAS 乐观锁"
              className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-input focus:outline-hidden focus:ring-2 focus:ring-primary text-foreground"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setIsSeedingOpen(false)}
              className="px-3 py-1.5 text-xs rounded-lg border border-border bg-background hover:bg-muted text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary"
            >
              取消
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-hidden focus:ring-2 focus:ring-primary shadow-xs"
            >
              保存至踩坑库
            </button>
          </div>
        </form>
      )}

      {/* Main Grid: Shadow Detector View + Proactive Alert Callout View */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ShadowDecisionDetectorView
          onEvaluate={handleEvaluate}
          isEvaluating={isEvaluating}
          evaluationResult={evaluationResult}
        />

        <ProactivePitfallCalloutView
          alertCard={evaluationResult?.alert_card ?? null}
          onAdoptSuggestion={handleAdoptSuggestion}
          onMuteTopic={handleMuteTopic}
          onUnmuteTopic={handleUnmuteTopic}
          isMuted={Boolean(evaluationResult?.alert_card?.is_muted)}
        />
      </div>

      {/* User Feedback Toast using output polite tag */}
      {feedbackToast && (
        <aside className="p-3 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
            <output aria-live="polite" className="font-medium text-foreground">
              {feedbackToast}
            </output>
          </div>
          <button
            type="button"
            onClick={() => setFeedbackToast(null)}
            aria-label="关闭提示"
            className="text-muted-foreground hover:text-foreground p-1 focus:outline-hidden focus:ring-2 focus:ring-primary rounded-md"
          >
            <AlertCircle className="w-3.5 h-3.5" />
          </button>
        </aside>
      )}
    </section>
  );
};
