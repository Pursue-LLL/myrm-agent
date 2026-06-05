'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  XCircle,
  ChevronRight,
  TrendingUp,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  Activity,
  Loader2,
  FlaskConical,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Progress } from '@/components/primitives/progress';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/primitives/alert-dialog';
import { toast } from '@/hooks/useToast';
import {
  getSkillVersionDetail,
  listSkillVersions,
  startShadowAbTest,
} from '@/services/skill-optimization';

interface ShadowSample {
  id: number;
  inputs: Record<string, unknown>;
  baseline_output: Record<string, unknown>;
  candidate_output: Record<string, unknown>;
  is_match: boolean;
  similarity_score: number | null;
  baseline_latency_ms: number;
  candidate_latency_ms: number;
  diff_summary: string | null;
  recorded_at: string;
}

interface ABTestStatus {
  id: string;
  skill_id: string;
  status: string;
  baseline_version: number;
  candidate_version: number;
  sample_size_current: number;
  sample_size_target: number;
  candidate_score?: {
    success_rate: number;
    avg_latency: number;
  };
  samples: ShadowSample[];
}

interface SkillQualityGuardianProps {
  skillId: string;
  onPromoted?: () => void;
  onStopped?: () => void;
}

function SimilarityBar({ score }: { score: number | null }) {
  if (score === null) return null;
  const pct = Math.round(score * 100);
  const color = pct >= 90 ? 'bg-green-500' : pct >= 70 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
        <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[9px] font-mono tabular-nums w-7 text-right">{pct}%</span>
    </div>
  );
}

function SampleCard({ sample, t }: { sample: ShadowSample; t: ReturnType<typeof useTranslations> }) {
  const [expanded, setExpanded] = useState(false);
  const latencyDelta = sample.candidate_latency_ms - sample.baseline_latency_ms;
  const latencyColor = latencyDelta <= 0 ? 'text-green-500' : latencyDelta > 100 ? 'text-red-400' : 'text-amber-400';

  return (
    <div className="p-2 rounded-lg bg-background/50 border border-border text-[11px] space-y-2">
      <div className="flex justify-between items-center">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="font-mono truncate max-w-[60%] text-left hover:underline cursor-pointer"
        >
          {JSON.stringify(sample.inputs).slice(0, 40)}...
        </button>
        <Badge variant={sample.is_match ? 'outline' : 'destructive'} className="h-4 px-1 text-[9px]">
          {sample.is_match ? t('match') : t('diverged')}
        </Badge>
      </div>

      {sample.similarity_score !== null && <SimilarityBar score={sample.similarity_score} />}

      {sample.diff_summary && !sample.is_match && (
        <div className="text-[10px] text-muted-foreground bg-destructive/5 px-2 py-1 rounded border-l-2 border-destructive/30">
          {sample.diff_summary}
        </div>
      )}

      {expanded && !sample.is_match && (
        <div className="grid grid-cols-2 gap-2 border-t pt-2 border-border/50 animate-in slide-in-from-top-1">
          <div className="space-y-1">
            <div className="text-primary font-bold text-[10px]">{t('baselineLabel')}</div>
            <pre className="bg-primary/5 p-1.5 rounded text-[10px] overflow-auto max-h-40 whitespace-pre-wrap break-all">
              {JSON.stringify(sample.baseline_output, null, 2)}
            </pre>
          </div>
          <div className="space-y-1">
            <div className="text-primary font-bold text-[10px]">{t('candidateLabel')}</div>
            <pre className="bg-primary/5 p-1.5 rounded text-[10px] overflow-auto max-h-40 whitespace-pre-wrap break-all">
              {JSON.stringify(sample.candidate_output, null, 2)}
            </pre>
          </div>
        </div>
      )}

      <div className="flex justify-between text-[9px] opacity-50">
        <span>{new Date(sample.recorded_at).toLocaleTimeString()}</span>
        <span className={latencyColor}>
          {latencyDelta > 0 ? '+' : ''}
          {latencyDelta.toFixed(1)}ms
        </span>
      </div>
    </div>
  );
}

export function SkillQualityGuardian({ skillId, onPromoted, onStopped }: SkillQualityGuardianProps) {
  const t = useTranslations('settings.skillOptimization.guardian');
  const [testStatus, setTestStatus] = useState<ABTestStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPromoting, setIsPromoting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [showSamples, setShowSamples] = useState(false);
  const [canStartShadow, setCanStartShadow] = useState(false);
  const [pendingCandidateVersion, setPendingCandidateVersion] = useState<number | null>(null);
  const [baselineVersion, setBaselineVersion] = useState<number | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const resp = await fetch(`/api/v1/skill-optimization/ab-tests/${skillId}/status?include_samples=true`);
      if (resp.ok) {
        const data = (await resp.json()) as ABTestStatus;
        setTestStatus(data);
        setCanStartShadow(false);
        return;
      }
      setTestStatus(null);

      const versionsResp = await listSkillVersions(skillId, 20);
      const active = versionsResp.versions.find((v) => v.is_active);
      const inactive = versionsResp.versions
        .filter((v) => !v.is_active)
        .sort((a, b) => b.version - a.version)[0];
      if (active && inactive && inactive.version > active.version) {
        setCanStartShadow(true);
        setBaselineVersion(active.version);
        setPendingCandidateVersion(inactive.version);
      } else {
        setCanStartShadow(false);
        setBaselineVersion(null);
        setPendingCandidateVersion(null);
      }
    } catch (error) {
      console.error('Failed to fetch AB test status:', error);
      setTestStatus(null);
      setCanStartShadow(false);
    } finally {
      setIsLoading(false);
    }
  }, [skillId]);

  useEffect(() => {
    void fetchStatus();
    const timer = setInterval(() => {
      if (testStatus && testStatus.status === 'RUNNING') {
        void fetchStatus();
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [fetchStatus, testStatus?.status]);

  const handleStartShadow = async () => {
    if (baselineVersion === null || pendingCandidateVersion === null) return;
    setIsStarting(true);
    try {
      const detail = await getSkillVersionDetail(skillId, pendingCandidateVersion);
      await startShadowAbTest(skillId, baselineVersion, detail.content);
      toast({ title: t('startSuccess') });
      await fetchStatus();
    } catch {
      toast({ title: t('startFailed'), variant: 'destructive' });
    } finally {
      setIsStarting(false);
    }
  };

  const handlePromote = async (version: number) => {
    setIsPromoting(true);
    try {
      const resp = await fetch(`/api/v1/skill-optimization/ab-tests/${skillId}/promote?version=${version}`, {
        method: 'POST',
      });
      if (resp.ok) {
        toast({ title: t('promoteSuccess', { version }) });
        onPromoted?.();
        await fetchStatus();
      } else {
        toast({ title: t('promoteFailed'), variant: 'destructive' });
      }
    } catch {
      toast({ title: t('networkError'), variant: 'destructive' });
    } finally {
      setIsPromoting(false);
    }
  };

  const handleStop = async () => {
    setIsStopping(true);
    try {
      const resp = await fetch(`/api/v1/skill-optimization/ab-tests/${skillId}/stop`, { method: 'POST' });
      if (resp.ok) {
        toast({ title: t('stopSuccess') });
        onStopped?.();
        await fetchStatus();
      } else {
        toast({ title: t('stopFailed'), variant: 'destructive' });
      }
    } catch {
      toast({ title: t('networkError'), variant: 'destructive' });
    } finally {
      setIsStopping(false);
    }
  };

  if (isLoading) {
    return (
      <div className="p-4 flex justify-center">
        <Loader2 className="animate-spin" />
      </div>
    );
  }

  if (!testStatus && canStartShadow && baselineVersion !== null && pendingCandidateVersion !== null) {
    return (
      <div className="space-y-3 p-4 rounded-xl border border-border/60 bg-card/40">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold">{t('idleTitle')}</h3>
        </div>
        <p className="text-xs text-muted-foreground">{t('idleDescription')}</p>
        <p className="text-xs font-mono text-muted-foreground">
          v{baselineVersion} → v{pendingCandidateVersion}
        </p>
        <Button size="sm" className="w-full" disabled={isStarting} onClick={() => void handleStartShadow()}>
          {isStarting ? <Loader2 className="animate-spin mr-2 h-4 w-4" /> : <FlaskConical className="mr-2 h-4 w-4" />}
          {t('startShadow')}
        </Button>
      </div>
    );
  }

  if (!testStatus) return null;

  const score = testStatus.candidate_score || { success_rate: 0, avg_latency: 0 };
  const matchRate = (score.success_rate * 100).toFixed(0);
  const progress = (testStatus.sample_size_current / testStatus.sample_size_target) * 100;

  return (
    <div className="space-y-4 p-4 rounded-xl border border-primary/20 bg-primary/5 dark:bg-primary/10">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={18} className="text-primary animate-pulse" />
          <h3 className="text-sm font-semibold">
            {t('runningTitle', {
              baseline: testStatus.baseline_version,
              candidate: testStatus.candidate_version,
            })}
          </h3>
        </div>
        <Badge variant={testStatus.status === 'RUNNING' ? 'default' : 'secondary'}>{testStatus.status}</Badge>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wider">{t('consistency')}</span>
          <div className="flex items-center gap-2">
            <span className={cn('text-lg font-bold', parseFloat(matchRate) > 90 ? 'text-green-500' : 'text-amber-500')}>
              {matchRate}%
            </span>
            {parseFloat(matchRate) > 95 ? (
              <ShieldCheck size={14} className="text-green-500" />
            ) : (
              <ShieldAlert size={14} className="text-amber-500" />
            )}
          </div>
        </div>
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wider">{t('samples')}</span>
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{testStatus.sample_size_current}</span>
            <span className="text-xs text-muted-foreground">/ {testStatus.sample_size_target}</span>
          </div>
        </div>
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wider">{t('versions')}</span>
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-primary font-bold">v{testStatus.baseline_version}</span>
            <ArrowRight size={10} className="text-muted-foreground" />
            <span className="text-accent-warm font-bold">v{testStatus.candidate_version}</span>
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex justify-between text-[11px] text-muted-foreground">
          <span>{t('confidence')}</span>
          <span>{progress.toFixed(0)}%</span>
        </div>
        <Progress value={progress} className="h-1" />
      </div>

      <div className="flex flex-col gap-2">
        <Button
          variant="outline"
          size="sm"
          className="w-full text-xs h-8 border-primary/30 hover:bg-primary/10"
          onClick={() => setShowSamples(!showSamples)}
        >
          {showSamples ? t('hideSamples') : t('reviewDifferences')}
          <ChevronRight size={14} className={cn('ml-1 transition-transform', showSamples && 'rotate-90')} />
        </Button>

        {showSamples && testStatus.samples?.length > 0 && (
          <div className="mt-2 space-y-2 animate-in slide-in-from-top-2">
            {testStatus.samples.map((sample) => (
              <SampleCard key={sample.id} sample={sample} t={t} />
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="flex-1 text-xs h-8 border-destructive/30 text-destructive hover:bg-destructive/10"
                disabled={isStopping || testStatus.status !== 'RUNNING'}
              >
                {isStopping ? <Loader2 className="animate-spin size-3 mr-2" /> : <XCircle size={14} className="mr-1" />}
                {t('stopTest')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('stopConfirmTitle')}</AlertDialogTitle>
                <AlertDialogDescription>
                  {t('stopConfirmDescription', {
                    skillId,
                    baseline: testStatus.baseline_version,
                  })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => void handleStop()}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {t('stopTest')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <Button
            variant="default"
            size="sm"
            className="flex-1 text-xs h-8 font-bold"
            disabled={isPromoting || parseFloat(matchRate) < 50}
            onClick={() => void handlePromote(testStatus.candidate_version)}
          >
            {isPromoting ? <Loader2 className="animate-spin size-3 mr-2" /> : <TrendingUp size={14} className="mr-1" />}
            {t('promote', { version: testStatus.candidate_version })}
          </Button>
        </div>
      </div>
    </div>
  );
}
