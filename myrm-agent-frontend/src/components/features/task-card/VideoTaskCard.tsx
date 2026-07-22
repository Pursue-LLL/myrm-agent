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
import { useTaskSubscription } from '@/hooks/tasks/useTasksSubscription';
import TaskCardPlaceholder from './TaskCardPlaceholder';
import TaskCardError from './TaskCardError';

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
            Video completed. Open the artifacts panel to view output. / 视频已完成，可在工件面板查看输出。
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
          Your browser does not support video playback. / 当前浏览器不支持视频播放。
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
                Alternate {index + 2} / 备用 {index + 2}
              </a>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {result.provider && <span>Provider / 提供商: {result.provider}</span>}
          {result.model && <span>Model / 模型: {result.model}</span>}
          {typeof result.latencyMs === 'number' && <span>Latency / 延迟: {Math.round(result.latencyMs)}ms</span>}
        </div>
      </div>
    );
    return className ? <div className={className}>{card}</div> : card;
  }

  if (task.status === 'failed' && task.error) {
    const handleRetry = async () => {
      try {
        await fetch(`/api/v1/tasks/${task_id}/retry`, { method: 'POST' });
      } catch (error) {
        console.error('Failed to retry task:', error);
      }
    };

    return (
      <TaskCardError
        error={task.error}
        onRetry={task.error.recoverable === 'transient' ? handleRetry : undefined}
        className={className}
      />
    );
  }

  if (task.status === 'cancelled') {
    return (
      <div className="rounded-lg border border-border/50 bg-muted/20 p-4">
        <p className="text-sm text-muted-foreground">Task cancelled / 任务已取消</p>
      </div>
    );
  }

  return null;
};

export default VideoTaskCard;
