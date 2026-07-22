/**
 * [INPUT]
 * @/hooks/tasks/useTasksSubscription::useTaskSubscription (POS: Task realtime subscription hook)
 * @/components/features/image-gen/ImageResultCard::ImageResultCard (POS: Image generation result renderer)
 * ./TaskCardPlaceholder (POS: Task pending/running placeholder card)
 * ./TaskCardError (POS: Task failure card)
 *
 * [OUTPUT]
 * ImageTaskCard: Renders an async image-generation task across loading, progress, success, failure and cancelled states.
 *
 * [POS]
 * Image task card with dynamic rendering.
 * It subscribes to task status by ID and converts successful task payloads into the image result card contract.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { useTaskSubscription } from '@/hooks/tasks/useTasksSubscription';
import { ImageResultCard } from '@/components/features/image-gen/ImageResultCard';
import TaskCardPlaceholder from './TaskCardPlaceholder';
import TaskCardError from './TaskCardError';
import type { ImageGenerationResult } from '@/store/tasks/types';
import { useTaskRetry } from './useTaskRetry';

interface ImageTaskCardProps {
  task_id: string;
  className?: string;
}

function normalizeImageGenerationResult(result: Record<string, unknown>): ImageGenerationResult | null {
  const rawImages = result.images;
  const model = result.model;
  const provider = result.provider;
  const latencyMs = result.latency_ms;

  if (!Array.isArray(rawImages) || typeof model !== 'string' || typeof provider !== 'string') {
    return null;
  }

  const images = rawImages
    .map((image): ImageGenerationResult['images'][number] | null => {
      if (typeof image !== 'object' || image === null) {
        return null;
      }
      const item = image as Record<string, unknown>;
      const url = item.url;
      if (typeof url !== 'string' || url.length === 0) {
        return null;
      }
      return {
        url,
        width: typeof item.width === 'number' ? item.width : undefined,
        height: typeof item.height === 'number' ? item.height : undefined,
        mime_type: typeof item.mime_type === 'string' ? item.mime_type : undefined,
      };
    })
    .filter((image): image is ImageGenerationResult['images'][number] => image !== null);

  if (images.length === 0) {
    return null;
  }

  return {
    images,
    model,
    provider,
    latency_ms: typeof latencyMs === 'number' ? latencyMs : undefined,
  };
}

function getStringPayloadValue(payload: Record<string, unknown>, key: string): string | undefined {
  const value = payload[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

export const ImageTaskCard: React.FC<ImageTaskCardProps> = ({ task_id, className }) => {
  const task = useTaskSubscription(task_id);
  const t = useTranslations('taskCard');
  const { isRetrying, retryErrorMessage, retry } = useTaskRetry(task_id, task?.status);

  // Loading state
  if (!task) {
    return <TaskCardPlaceholder className={className} />;
  }

  // Pending or running state
  if (task.status === 'pending' || task.status === 'queued' || task.status === 'running') {
    return (
      <TaskCardPlaceholder prompt={getStringPayloadValue(task.payload, 'prompt')} progress={task.progress} className={className} />
    );
  }

  // Success state
  if (task.status === 'succeeded' && task.result) {
    const result = normalizeImageGenerationResult(task.result);
    if (!result) {
      return null;
    }

    const card = (
      <ImageResultCard
        images={result.images.map((img) => ({
          url: img.url,
          mimeType: img.mime_type,
        }))}
        prompt={getStringPayloadValue(task.payload, 'prompt')}
        model={result.model}
        size={getStringPayloadValue(task.payload, 'size')}
        latencyMs={result.latency_ms}
      />
    );
    return className ? <div className={className}>{card}</div> : card;
  }

  // Failed state
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

  // Cancelled state
  if (task.status === 'cancelled') {
    return (
      <div className="rounded-lg border border-border/50 bg-muted/20 p-4">
        <p className="text-sm text-muted-foreground">{t('cancelled')}</p>
      </div>
    );
  }

  return null;
};

export default ImageTaskCard;
