/**
 * [INPUT]
 * @/hooks/tasks/useTasksSubscription::useTaskSubscription (POS: Task realtime subscription hook)
 * ./TaskCardPlaceholder (POS: Task pending/running placeholder card)
 * ./TaskCardError (POS: Task failure card)
 *
 * [OUTPUT]
 * VideoTaskCard: Renders an async video-generation task across loading, progress, success, failure and cancelled states.
 *
 * [POS]
 * Video task card with dynamic rendering. It subscribes to task status by ID and
 * renders a playable preview when persisted video URLs are available.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { useTaskSubscription } from '@/hooks/tasks/useTasksSubscription';
import TaskCardPlaceholder from './TaskCardPlaceholder';
import TaskCardError from './TaskCardError';
import { useTaskRetry } from './useTaskRetry';

interface VideoTaskCardProps {
  task_id: string;
  className?: string;
}

interface NormalizedVideoResult {
  videoUrls: string[];
  provider?: string;
  model?: string;
  latencyMs?: number;
}

function normalizeVideoResult(result: Record<string, unknown>): NormalizedVideoResult | null {
  const urlsRaw = result.video_urls;
  if (!Array.isArray(urlsRaw)) {
    return null;
  }
  const videoUrls = urlsRaw.filter((item): item is string => typeof item === 'string' && item.length > 0);
  if (videoUrls.length === 0) {
    return null;
  }
  const provider = typeof result.provider === 'string' ? result.provider : undefined;
  const model = typeof result.model === 'string' ? result.model : undefined;
  const latencyMs = typeof result.latency_ms === 'number' ? result.latency_ms : undefined;
  return { videoUrls, provider, model, latencyMs };
}

function getStringPayloadValue(payload: Record<string, unknown>, key: string): string | undefined {
  const value = payload[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

export const VideoTaskCard: React.FC<VideoTaskCardProps> = ({ task_id, className }) => {
  const task = useTaskSubscription(task_id);
  const t = useTranslations('taskCard');
  const { isRetrying, retryErrorMessage, retry } = useTaskRetry(task_id, task?.status);

  if (!task) {
    return <TaskCardPlaceholder className={className} />;
  }

  if (task.status === 'pending' || task.status === 'queued' || task.status === 'running') {
    return (
      <TaskCardPlaceholder prompt={getStringPayloadValue(task.payload, 'prompt')} progress={task.progress} className={className} />
    );
  }

  if (task.status === 'succeeded' && task.result) {
    const result = normalizeVideoResult(task.result);
    if (!result) {
      return (
        <div className="rounded-lg border border-border/50 bg-muted/20 p-4">
          <p className="text-sm text-muted-foreground">
            {t('videoCompletedFallback')}
          </p>
        </div>
      );
    }

    const card = (
      <div className="rounded-lg border border-border/50 bg-card p-4 space-y-3">
        <video
          controls
          className="w-full rounded-md bg-black/80"
          src={result.videoUrls[0]}
          preload="metadata"
        >
          {t('videoUnsupported')}
        </video>
        {result.videoUrls.length > 1 && (
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {result.videoUrls.slice(1).map((url, index) => (
              <a
                key={url}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2 hover:text-foreground"
              >
                {t('alternateLabel', { index: index + 2 })}
              </a>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {result.provider && <span>{t('providerLabel')}: {result.provider}</span>}
          {result.model && <span>{t('modelLabel')}: {result.model}</span>}
          {typeof result.latencyMs === 'number' && <span>{t('latencyLabel')}: {Math.round(result.latencyMs)}ms</span>}
        </div>
      </div>
    );
    return className ? <div className={className}>{card}</div> : card;
  }

  if (task.status === 'failed' && task.error) {
    return (
      <TaskCardError
        error={task.error}
        onRetry={task.error.recoverable === 'transient' ? retry : undefined}
        isRetrying={isRetrying}
        retryErrorMessage={retryErrorMessage}
        className={className}
      />
    );
  }

  if (task.status === 'cancelled') {
    return (
      <div className="rounded-lg border border-border/50 bg-muted/20 p-4">
        <p className="text-sm text-muted-foreground">{t('cancelled')}</p>
      </div>
    );
  }

  return null;
};

export default VideoTaskCard;
