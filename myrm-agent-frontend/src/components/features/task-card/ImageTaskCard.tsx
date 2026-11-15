/**
 * [INPUT]
 * @/hooks/tasks/useTasksSubscription::useTaskSubscription (POS: Task realtime subscription hook)
 * @/components/features/image-gen/ImageResultCard::ImageResultCard (POS: Image generation result renderer)
 * @/components/features/image-gen/useEditGeneratedImage::useEditGeneratedImage (POS: Edit-this-image composer action)
 * @/lib/mediaReference::parseMediaReference (POS: Reads the id out of a `media://<id>` reference)
 * ./TaskCardPlaceholder (POS: Task pending/running placeholder card)
 * ./TaskCardError (POS: Task failure card)
 * ./TaskCardNotice / ./TaskCardExpired (POS: Result-less task states)
 *
 * [OUTPUT]
 * ImageTaskCard: Renders an async image-generation task across loading, progress, success, failure, cancelled and
 * expired states.
 *
 * [POS]
 * Image task card with dynamic rendering.
 * It subscribes to task status by ID and converts successful task payloads into the image result card contract.
 * The edit action is offered only for images that live in the media library, because only those can be referenced.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { useTaskSubscription } from '@/hooks/tasks/useTasksSubscription';
import { cancelMediaTask } from '@/services/mediaTasks';
import { ImageResultCard } from '@/components/features/image-gen/ImageResultCard';
import { useEditGeneratedImage } from '@/components/features/image-gen/useEditGeneratedImage';
import { parseMediaReference } from '@/lib/mediaReference';
import TaskCardPlaceholder from './TaskCardPlaceholder';
import TaskCardError from './TaskCardError';
import TaskCardExpired from './TaskCardExpired';
import TaskCardNotice from './TaskCardNotice';
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

  if (!Array.isArray(rawImages) || typeof model !== 'string') {
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
    provider: typeof provider === 'string' ? provider : undefined,
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
  const editImage = useEditGeneratedImage();
  const { isRetrying, retryErrorMessage, retry } = useTaskRetry(task_id, task?.status);

  // Loading state
  if (task === undefined) {
    return <TaskCardPlaceholder className={className} />;
  }

  // The record was pruned; the image itself stays in the media library
  if (task === null) {
    return <TaskCardExpired className={className} />;
  }

  // Pending or running state
  if (task.status === 'pending' || task.status === 'queued' || task.status === 'running') {
    return (
      <TaskCardPlaceholder
        taskId={task.task_id}
        prompt={getStringPayloadValue(task.payload, 'prompt')}
        progress={task.progress}
        onCancel={cancelMediaTask}
        className={className}
      />
    );
  }

  // Success state
  if (task.status === 'succeeded') {
    const result = task.result ? normalizeImageGenerationResult(task.result) : null;
    if (!result) {
      return <TaskCardNotice className={className}>{t('resultUnavailable')}</TaskCardNotice>;
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
        onEditRequest={parseMediaReference(result.images[0].url) ? editImage : undefined}
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
    return <TaskCardNotice className={className}>{t('cancelled')}</TaskCardNotice>;
  }

  return null;
};

export default ImageTaskCard;
