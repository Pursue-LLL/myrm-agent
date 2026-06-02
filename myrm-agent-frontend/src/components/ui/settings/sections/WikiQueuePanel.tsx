'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { IconCheckCircle, IconXCircle, IconRotateCcw } from '@/components/ui/icons/PremiumIcons';
import { apiRequest } from '@/lib/api';

interface QueueStats {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
}

interface QueueStatusResponse {
  stats: QueueStats;
  pending_items: Array<{
    id: number;
    file_path: string;
    status: string;
    retry_count: number;
    created_at: string;
  }>;
}

export function WikiQueuePanel() {
  const t = useTranslations('settings.wiki.queue');
  const [queueData, setQueueData] = useState<QueueStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  const loadQueue = async () => {
    setIsLoading(true);
    try {
      const data = await apiRequest<QueueStatusResponse>('/wiki/queue');
      setQueueData(data);
    } catch (error) {
      console.error('Failed to load queue:', error);
      toast.error(t('loadFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
  }, []);

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      await apiRequest('/wiki/queue/cancel', { method: 'POST' });
      toast.success(t('cancelSuccess'));
      await loadQueue();
    } catch (error) {
      console.error('Failed to cancel queue:', error);
      toast.error(t('cancelFailed'));
    } finally {
      setIsCancelling(false);
    }
  };

  const handleRetry = async () => {
    setIsRetrying(true);
    try {
      await apiRequest('/wiki/queue/retry', { method: 'POST' });
      toast.success(t('retrySuccess'));
      await loadQueue();
    } catch (error) {
      console.error('Failed to retry queue:', error);
      toast.error(t('retryFailed'));
    } finally {
      setIsRetrying(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconCheckCircle className="w-5 h-5" />
          {t('title')}
        </CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading && !queueData ? (
          <div className="text-center py-4 text-muted-foreground">{t('loading')}</div>
        ) : queueData ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="text-center p-3 bg-yellow-500/10 rounded-lg">
                <div className="text-2xl font-bold text-yellow-600">{queueData.stats.pending}</div>
                <div className="text-xs text-muted-foreground">{t('statsPending')}</div>
              </div>
              <div className="text-center p-3 bg-blue-500/10 rounded-lg">
                <div className="text-2xl font-bold text-blue-600">{queueData.stats.processing}</div>
                <div className="text-xs text-muted-foreground">{t('statsProcessing')}</div>
              </div>
              <div className="text-center p-3 bg-green-500/10 rounded-lg">
                <div className="text-2xl font-bold text-green-600">{queueData.stats.completed}</div>
                <div className="text-xs text-muted-foreground">{t('statsCompleted')}</div>
              </div>
              <div className="text-center p-3 bg-red-500/10 rounded-lg">
                <div className="text-2xl font-bold text-red-600">{queueData.stats.failed}</div>
                <div className="text-xs text-muted-foreground">{t('statsFailed')}</div>
              </div>
            </div>

            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancel}
                disabled={isCancelling || queueData.stats.pending === 0}
              >
                <IconXCircle className="w-4 h-4 mr-1" />
                {isCancelling ? t('cancelling') : t('cancelAll')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRetry}
                disabled={isRetrying || queueData.stats.failed === 0}
              >
                <IconRotateCcw className="w-4 h-4 mr-1" />
                {isRetrying ? t('retrying') : t('retryFailed')}
              </Button>
              <Button variant="ghost" size="sm" onClick={loadQueue}>
                {t('refresh')}
              </Button>
            </div>

            {queueData.pending_items.length > 0 && (
              <div className="mt-4 space-y-2">
                <div className="text-sm font-medium">{t('pendingItems')}</div>
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {queueData.pending_items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between px-3 py-2 bg-muted rounded text-xs">
                      <span className="truncate max-w-[70%]">{item.file_path.split('/').pop()}</span>
                      <span className="text-muted-foreground">{item.retry_count > 0 && `×${item.retry_count}`}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
