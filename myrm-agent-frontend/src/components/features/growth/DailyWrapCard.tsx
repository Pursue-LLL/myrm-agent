'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { AlertCircle, Loader2, RefreshCw, Settings, Sparkles, Tag } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import { getDailyWrap, regenerateDailyWrap, type DailyWrapData } from '@/services/statistics';
import { showApiError } from '@/lib/api';

interface DailyWrapCardProps {
  date: string;
}

export default function DailyWrapCard({ date }: DailyWrapCardProps) {
  const t = useTranslations('growthDashboard.dailyWrap');
  const router = useRouter();
  const [data, setData] = useState<DailyWrapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState(false);

  const fetchWrap = useCallback(async () => {
    try {
      setLoading(true);
      setError(false);
      const result = await getDailyWrap(date);
      setData(result);
    } catch (e) {
      showApiError(e);
      setError(true);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    fetchWrap();
  }, [fetchWrap]);

  const handleRegenerate = async () => {
    try {
      setRegenerating(true);
      const result = await regenerateDailyWrap(date);
      setData(result);
    } catch (e) {
      showApiError(e);
    } finally {
      setRegenerating(false);
    }
  };

  if (loading) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex items-center justify-center py-6">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mr-2" />
          <span className="text-sm text-muted-foreground">{t('loading')}</span>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="border-destructive/30">
        <CardContent className="flex items-center justify-center py-4 gap-2">
          <AlertCircle className="h-4 w-4 text-destructive" />
          <span className="text-sm text-muted-foreground">{t('error')}</span>
        </CardContent>
      </Card>
    );
  }

  if (!data?.summary) {
    if (data?.reason === 'lite_model_not_configured') {
      return (
        <Card className="border-dashed">
          <CardContent className="flex items-center justify-center py-4 gap-2">
            <span className="text-xs text-muted-foreground">{t('noModel')}</span>
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={() => router.push('/settings/models')}
            >
              <Settings className="h-3 w-3 mr-1" />
              {t('goToSettings')}
            </Button>
          </CardContent>
        </Card>
      );
    }
    return null;
  }

  return (
    <Card className="bg-gradient-to-br from-primary/5 to-transparent border-primary/20">
      <CardHeader className="pb-2 px-4 pt-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
            <Sparkles className="h-4 w-4 text-primary" />
            {t('title')}
          </CardTitle>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleRegenerate}
            disabled={regenerating}
            title={t('regenerate')}
          >
            <RefreshCw className={cn('h-3 w-3', regenerating && 'animate-spin')} />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <p className="text-sm text-foreground leading-relaxed">{data.summary}</p>

        {data.keywords.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <Tag className="h-3 w-3 text-muted-foreground shrink-0" />
            {data.keywords.map((kw) => (
              <Badge key={kw} variant="secondary" className="text-[10px] px-1.5 py-0">
                {kw}
              </Badge>
            ))}
          </div>
        )}

        {data.suggestions.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
              {t('suggestions')}
            </p>
            <ul className="space-y-0.5">
              {data.suggestions.map((s, i) => (
                <li key={i} className="text-xs text-muted-foreground pl-3 relative before:content-[''] before:absolute before:left-0 before:top-[7px] before:h-1 before:w-1 before:rounded-full before:bg-primary/40">
                  {s}
                </li>
              ))}
            </ul>
          </div>
        )}

        {data.generated_at && (
          <p className="text-[10px] text-muted-foreground/60 text-right">
            {t('generatedAt')} {new Date(data.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
