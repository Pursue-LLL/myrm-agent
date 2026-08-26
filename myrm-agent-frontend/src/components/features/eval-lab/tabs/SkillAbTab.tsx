import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Award, CheckCircle2, ChevronRight, Play, ShieldAlert, Sparkles, Zap } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { evalService, type SkillABReport } from '@/services/eval';
import { toast } from 'sonner';

interface SkillAbTabProps {
  datasetId: string;
}

export default function SkillAbTab({ datasetId }: SkillAbTabProps) {
  const t = useTranslations('evalLab');
  const [candidateSkillId, setCandidateSkillId] = useState('');
  const [baselineSkillId, setBaselineSkillId] = useState('');
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<SkillABReport | null>(null);

  const handleRun = async () => {
    if (!candidateSkillId.trim()) {
      toast.error(t('skillAb.candidateRequired'));
      return;
    }
    setRunning(true);
    try {
      await evalService.runSkillAb({
        benchmark_id: datasetId,
        candidate_skill_id: candidateSkillId.trim(),
        baseline_skill_id: baselineSkillId.trim() || null,
      });
      toast.success(t('skillAb.started'));
      
      // Poll until completion
      const interval = setInterval(async () => {
        try {
          const status = await evalService.getSkillAbStatus();
          if (!status.is_running) {
            clearInterval(interval);
            setRunning(false);
            if (status.error) {
              toast.error(status.error);
            } else {
              const latest = await evalService.getLatestSkillAbReport();
              setReport(latest);
            }
          }
        } catch {
          clearInterval(interval);
          setRunning(false);
        }
      }, 2000);
    } catch (e: unknown) {
      setRunning(false);
      toast.error((e as Error).message || 'Failed to start Skill A/B');
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto p-4">
      {/* Control Card */}
      <div className="p-4 rounded-xl border border-border/80 bg-muted/20 space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" />
          <h3 className="font-semibold text-sm">{t('skillAb.title')}</h3>
        </div>
        <p className="text-xs text-muted-foreground">{t('skillAb.description')}</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-foreground mb-1 block">
              {t('skillAb.candidateSkillLabel')}
            </label>
            <Input
              value={candidateSkillId}
              onChange={(e) => setCandidateSkillId(e.target.value)}
              placeholder="e.g. wechat-formatter-v2"
              className="text-xs font-mono"
              disabled={running}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground mb-1 block">
              {t('skillAb.baselineSkillLabel')}
            </label>
            <Input
              value={baselineSkillId}
              onChange={(e) => setBaselineSkillId(e.target.value)}
              placeholder="e.g. wechat-formatter-v1 (optional)"
              className="text-xs font-mono"
              disabled={running}
            />
          </div>
        </div>

        <div className="flex justify-end">
          <Button onClick={handleRun} disabled={running} size="sm" className="gap-2 text-xs">
            {running ? <Zap className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            {running ? t('skillAb.evaluating') : t('skillAb.startEval')}
          </Button>
        </div>
      </div>

      {/* Report View */}
      {report && (
        <div className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg bg-primary/10 border border-primary/20 text-xs">
            <div className="flex items-center gap-2">
              <Award className="w-4 h-4 text-primary" />
              <span className="font-semibold">{t('skillAb.verdict')}:</span>
              <span className="font-mono px-2 py-0.5 rounded bg-background text-primary font-bold">
                {report.verdict}
              </span>
            </div>
            <div className="text-muted-foreground font-mono">
              Delta: {(report.success_rate_delta * 100).toFixed(1)}% | Savings: {(report.token_savings_pct * 100).toFixed(1)}%
            </div>
          </div>

          {/* Three Arm Comparison Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* No-Skill Arm */}
            <div className="p-4 rounded-xl border border-border bg-card space-y-2 text-xs">
              <div className="font-semibold text-muted-foreground">{t('skillAb.armNoSkill')}</div>
              <div className="text-2xl font-bold font-mono">
                {(report.no_skill_metrics.pass_rate * 100).toFixed(1)}%
              </div>
              <div className="text-[11px] text-muted-foreground space-y-1 pt-2 border-t border-border">
                <div>{t('skillAb.avgSteps')}: {report.no_skill_metrics.avg_tool_calls}</div>
                <div>{t('skillAb.tokens')}: {report.no_skill_metrics.total_tokens.toLocaleString()}</div>
                <div>{t('skillAb.latency')}: {report.no_skill_metrics.avg_latency_ms.toFixed(0)}ms</div>
              </div>
            </div>

            {/* Baseline Arm */}
            <div className="p-4 rounded-xl border border-border bg-card space-y-2 text-xs">
              <div className="font-semibold text-muted-foreground">
                {t('skillAb.armBaseline')} ({report.baseline_metrics.skill_id || 'None'})
              </div>
              <div className="text-2xl font-bold font-mono">
                {(report.baseline_metrics.pass_rate * 100).toFixed(1)}%
              </div>
              <div className="text-[11px] text-muted-foreground space-y-1 pt-2 border-t border-border">
                <div>{t('skillAb.avgSteps')}: {report.baseline_metrics.avg_tool_calls}</div>
                <div>{t('skillAb.tokens')}: {report.baseline_metrics.total_tokens.toLocaleString()}</div>
                <div>{t('skillAb.latency')}: {report.baseline_metrics.avg_latency_ms.toFixed(0)}ms</div>
              </div>
            </div>

            {/* Candidate Arm */}
            <div className="p-4 rounded-xl border border-primary/50 bg-primary/5 space-y-2 text-xs">
              <div className="font-semibold text-primary">
                {t('skillAb.armCandidate')} ({report.candidate_metrics.skill_id})
              </div>
              <div className="text-2xl font-bold font-mono text-primary">
                {(report.candidate_metrics.pass_rate * 100).toFixed(1)}%
              </div>
              <div className="text-[11px] text-muted-foreground space-y-1 pt-2 border-t border-primary/20">
                <div>{t('skillAb.avgSteps')}: {report.candidate_metrics.avg_tool_calls}</div>
                <div>{t('skillAb.tokens')}: {report.candidate_metrics.total_tokens.toLocaleString()}</div>
                <div>{t('skillAb.latency')}: {report.candidate_metrics.avg_latency_ms.toFixed(0)}ms</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
