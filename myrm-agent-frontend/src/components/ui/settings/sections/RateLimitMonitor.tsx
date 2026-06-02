import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchRateLimits, RateLimitState, RateLimitBucket } from '@/services/rate-limits';

const CircularProgress = ({ value, label, colorClass }: { value: number; label: string; colorClass: string }) => {
  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (value / 100) * circumference;

  return (
    <div className="relative flex flex-col items-center justify-center">
      <svg className="w-20 h-20 transform -rotate-90">
        <circle
          className="text-muted/20"
          strokeWidth="6"
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx="40"
          cy="40"
        />
        <circle
          className={`${colorClass} transition-all duration-500 ease-in-out`}
          strokeWidth="6"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx="40"
          cy="40"
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center text-center">
        <span className="text-sm font-bold">{Math.round(value)}%</span>
      </div>
      <span className="mt-2 text-xs text-muted-foreground font-medium">{label}</span>
    </div>
  );
};

const BucketCard = ({ bucket, title }: { bucket: RateLimitBucket | null; title: string }) => {
  const [localRemainingSeconds, setLocalRemainingSeconds] = useState(bucket?.remaining_seconds_now || 0);

  useEffect(() => {
    if (!bucket) return;
    setLocalRemainingSeconds(bucket.remaining_seconds_now);

    // Setup local tick-down for a smooth UI experience
    const interval = setInterval(() => {
      setLocalRemainingSeconds((prev) => Math.max(0, prev - 1));
    }, 1000);

    return () => clearInterval(interval);
  }, [bucket]);

  if (!bucket) return null;

  const usagePct = bucket.usage_pct * 100;
  let colorClass = 'text-green-500';
  if (usagePct >= 80) colorClass = 'text-red-500';
  else if (usagePct >= 50) colorClass = 'text-yellow-500';

  return (
    <div className="flex flex-col items-center p-4 bg-muted/10 rounded-lg border border-border/50">
      <CircularProgress value={usagePct} label={title} colorClass={colorClass} />
      <div className="mt-3 text-xs text-center space-y-1">
        <div className="text-muted-foreground">
          <span className="font-medium text-foreground">{bucket.remaining}</span> / {bucket.limit}
        </div>
        {localRemainingSeconds > 0 && (
          <div className="text-muted-foreground/70">Resets in {Math.ceil(localRemainingSeconds)}s</div>
        )}
      </div>
    </div>
  );
};

export const RateLimitMonitor = () => {
  const t = useTranslations('settings.rate_limits');
  const [states, setStates] = useState<RateLimitState[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      try {
        const data = await fetchRateLimits();
        if (mounted) {
          setStates(data.states);
          setLoading(false);
        }
      } catch (error) {
        console.error('Failed to fetch rate limits:', error);
        if (mounted) setLoading(false);
      }
    };

    loadData();

    // Listen for SSE updates dispatched via custom event from messageStreamHandler
    const handleUpdate = () => {
      loadData();
    };

    window.addEventListener('rate_limit_updated', handleUpdate);

    return () => {
      mounted = false;
      window.removeEventListener('rate_limit_updated', handleUpdate);
    };
  }, []);

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 flex justify-center items-center h-40">
          <div className="w-6 h-6 animate-pulse rounded-full bg-muted-foreground/20" />
        </CardContent>
      </Card>
    );
  }

  if (states.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <div className="w-4 h-4 rounded-full border-2 border-primary/50" />
            {t('title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground text-center py-8">{t('no_data')}</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {states.map((state) => (
        <Card key={`${state.provider}-${state.model}`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded-full bg-primary/20 flex items-center justify-center">
                  <div className="w-2 h-2 rounded-full bg-primary" />
                </div>
                <span>{state.provider}</span>
                <span className="text-muted-foreground font-normal">({state.model})</span>
              </div>
              {state.highest_usage_pct >= 0.8 ? (
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" title="High Usage Warning" />
              ) : (
                <div className="w-2 h-2 rounded-full bg-green-500" title="Healthy" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <BucketCard bucket={state.rpm} title={t('requests_per_minute')} />
              <BucketCard bucket={state.rph} title={t('requests_per_hour')} />
              <BucketCard bucket={state.tpm} title={t('tokens_per_minute')} />
              <BucketCard bucket={state.tph} title={t('tokens_per_hour')} />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};
