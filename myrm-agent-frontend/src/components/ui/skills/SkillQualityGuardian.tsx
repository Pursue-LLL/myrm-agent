'use client';

import { useState, useEffect, useCallback } from 'react';
import { XCircle, ChevronRight, TrendingUp, ArrowRight, ShieldCheck, ShieldAlert, Activity } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
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
} from '@/components/ui/alert-dialog';
import { toast } from '@/hooks/useToast';
import { Loader2 } from 'lucide-react';

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

function SampleCard({ sample }: { sample: ShadowSample }) {
  const [expanded, setExpanded] = useState(false);
  const latencyDelta = sample.candidate_latency_ms - sample.baseline_latency_ms;
  const latencyColor = latencyDelta <= 0 ? 'text-green-500' : latencyDelta > 100 ? 'text-red-400' : 'text-amber-400';

  return (
    <div className="p-2 rounded-lg bg-background/50 border border-border text-[11px] space-y-2">
      <div className="flex justify-between items-center">
        <button
          onClick={() => setExpanded(!expanded)}
          className="font-mono truncate max-w-[60%] text-left hover:underline cursor-pointer"
        >
          {JSON.stringify(sample.inputs).slice(0, 40)}...
        </button>
        <div className="flex items-center gap-1.5">
          <Badge variant={sample.is_match ? 'outline' : 'destructive'} className="h-4 px-1 text-[9px]">
            {sample.is_match ? 'MATCH' : 'DIVERGED'}
          </Badge>
        </div>
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
            <div className="text-primary font-bold text-[10px]">BASELINE</div>
            <pre className="bg-primary/5 p-1.5 rounded text-[10px] overflow-auto max-h-40 whitespace-pre-wrap break-all">
              {JSON.stringify(sample.baseline_output, null, 2)}
            </pre>
          </div>
          <div className="space-y-1">
            <div className="text-primary font-bold text-[10px]">CANDIDATE</div>
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
  const [testStatus, setTestStatus] = useState<ABTestStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPromoting, setIsPromoting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [showSamples, setShowSamples] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const resp = await fetch(`/api/v1/skill-optimization/ab-tests/${skillId}/status?include_samples=true`);
      if (resp.ok) {
        const data = await resp.json();
        setTestStatus(data);
      } else {
        setTestStatus(null);
      }
    } catch (error) {
      console.error('Failed to fetch AB test status:', error);
    } finally {
      setIsLoading(false);
    }
  }, [skillId]);

  useEffect(() => {
    fetchStatus();
    // Poll for updates if testing is active
    const timer = setInterval(() => {
      if (testStatus && testStatus.status === 'RUNNING') {
        fetchStatus();
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [fetchStatus, testStatus?.status]);

  const handlePromote = async (version: number) => {
    setIsPromoting(true);
    try {
      const resp = await fetch(`/api/v1/skill-optimization/ab-tests/${skillId}/promote?version=${version}`, {
        method: 'POST',
      });
      if (resp.ok) {
        toast({ title: 'Success', description: `Version v${version} is now the active master.` });
        onPromoted?.();
        fetchStatus();
      } else {
        toast({ title: 'Error', description: 'Failed to promote version.', variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Error', description: 'Network error.', variant: 'destructive' });
    } finally {
      setIsPromoting(false);
    }
  };

  const handleStop = async () => {
    setIsStopping(true);
    try {
      const resp = await fetch(`/api/v1/skill-optimization/ab-tests/${skillId}/stop`, {
        method: 'POST',
      });
      if (resp.ok) {
        toast({ title: 'Test Stopped', description: 'A/B test has been stopped. Baseline remains active.' });
        onStopped?.();
        fetchStatus();
      } else {
        toast({ title: 'Error', description: 'Failed to stop test.', variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Error', description: 'Network error.', variant: 'destructive' });
    } finally {
      setIsStopping(false);
    }
  };

  if (isLoading)
    return (
      <div className="p-4 flex justify-center">
        <Loader2 className="animate-spin" />
      </div>
    );
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
            Shadow Test: v{testStatus.baseline_version} vs v{testStatus.candidate_version}
          </h3>
        </div>
        <Badge variant={testStatus.status === 'RUNNING' ? 'default' : 'secondary'} className="animate-in fade-in">
          {testStatus.status}
        </Badge>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wider">Consistency</span>
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
          <span className="text-xs text-muted-foreground uppercase tracking-wider">Samples</span>
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{testStatus.sample_size_current}</span>
            <span className="text-xs text-muted-foreground">/ {testStatus.sample_size_target}</span>
          </div>
        </div>
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wider">Versions</span>
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-primary font-bold">v{testStatus.baseline_version}</span>
            <ArrowRight size={10} className="text-muted-foreground" />
            <span className="text-accent-warm font-bold">v{testStatus.candidate_version}</span>
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex justify-between text-[11px] text-muted-foreground">
          <span>Test Confidence</span>
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
          {showSamples ? 'Hide Samples' : 'Review Differences'}
          <ChevronRight size={14} className={cn('ml-1 transition-transform', showSamples && 'rotate-90')} />
        </Button>

        {showSamples && testStatus.samples?.length > 0 && (
          <div className="mt-2 space-y-2 animate-in slide-in-from-top-2">
            {testStatus.samples.map((sample) => (
              <SampleCard key={sample.id} sample={sample} />
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
                Stop Test
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Stop A/B Test?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will stop the shadow test for skill "{skillId}". The baseline version (v
                  {testStatus.baseline_version}) will remain active.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleStop}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  Stop Test
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <Button
            variant="default"
            size="sm"
            className="flex-1 text-xs h-8 font-bold"
            disabled={isPromoting || parseFloat(matchRate) < 50}
            onClick={() => handlePromote(testStatus.candidate_version)}
          >
            {isPromoting ? <Loader2 className="animate-spin size-3 mr-2" /> : <TrendingUp size={14} className="mr-1" />}
            Promote v{testStatus.candidate_version}
          </Button>
        </div>
      </div>
    </div>
  );
}
