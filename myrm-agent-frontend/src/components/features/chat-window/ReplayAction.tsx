'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Play, CheckCircle2, AlertTriangle, RefreshCw, Layers } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/shared/useToast';
import { replayChatSession, type ReplayDeterminismResponse } from '@/services/chat';
import TrajectoryDiffModal from './TrajectoryDiffModal';

/** A replay that scores at least this well counts as deterministic. */
const DETERMINISTIC_THRESHOLD = 0.95;

const toPercent = (score: number) => (score * 100).toFixed(0);

interface ReplayActionProps {
  chatId: string;
}

export default function ReplayAction({ chatId }: ReplayActionProps) {
  const t = useTranslations('replayAction');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ReplayDeterminismResponse | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);

  const handleReplay = async () => {
    try {
      setLoading(true);
      const res = await replayChatSession(chatId);
      setResult(res);
      const score = toPercent(res.determinism_score);
      if (res.determinism_score >= DETERMINISTIC_THRESHOLD) {
        toast.success(t('replaySuccessDeterministic', { score }));
      } else {
        toast.warning(t('replaySuccessDrift', { score }));
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t('replayFailed'));
    } finally {
      setLoading(false);
    }
  };

  const deterministic = result !== null && result.determinism_score >= DETERMINISTIC_THRESHOLD;

  return (
    <div className="inline-flex items-center gap-1.5">
      <Button
        variant="outline"
        size="sm"
        disabled={loading}
        onClick={handleReplay}
        className="h-7 px-2 text-xs gap-1 border-border/50 hover:bg-muted/60"
        title={t('tooltip')}
      >
        {loading ? (
          <RefreshCw className="h-3.5 w-3.5 animate-spin text-primary" />
        ) : (
          <Play className="h-3.5 w-3.5 text-primary" />
        )}
        <span>{loading ? t('replaying') : t('replayButton')}</span>
      </Button>

      {result && (
        <button
          type="button"
          onClick={() => setDiffOpen(true)}
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-mono cursor-pointer border transition-all ${
            deterministic
              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
              : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30'
          }`}
          title={t('badgeTitle')}
        >
          {deterministic ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
          <span>{t('matchScore', { score: toPercent(result.determinism_score) })}</span>
        </button>
      )}

      {diffOpen && <TrajectoryDiffModal open={diffOpen} currentSessionId={chatId} onClose={() => setDiffOpen(false)} />}
    </div>
  );
}
