'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconRoute } from '@/components/features/icons/PremiumIcons';
import { checkVideoFallbackHealth } from '@/services/llm-config';
import MediaFallbackCard, { useFallbackHealthCheck, type MediaFallbackCopy } from './MediaFallbackCard';

const VideoFallbackCard = memo(() => {
  const t = useTranslations('settings.defaultModel');
  const health = useFallbackHealthCheck(checkVideoFallbackHealth, t('videoHealthNetworkError'));

  const copy: MediaFallbackCopy = {
    title: t('videoFallbackModel'),
    description: t('videoFallbackModelDescription'),
    fallbackDescription: t('videoFallbackModelFallbackDescription'),
    selectFallback: t('selectVideoFallbackModel'),
    health: {
      test: t('videoHealthTest'),
      checking: t('videoHealthChecking'),
      unknown: t('videoHealthUnknown'),
      notConfigured: t('videoHealthNotConfigured'),
      okHint: t('videoHealthOkHint'),
      ok: (latency) => t('videoHealthOk', { latency }),
      failed: (error) => t('videoHealthFailed', { error }),
      failedModel: (model) => t('videoHealthFailedModel', { model }),
      failedEndpoint: (endpoint) => t('videoHealthFailedEndpoint', { endpoint }),
      resolvedModel: (configured, resolved) => t('videoHealthResolvedModel', { configured, resolved }),
    },
  };

  return (
    <MediaFallbackCard
      icon={<IconRoute className="w-4 h-4 text-sky-500" />}
      copy={copy}
      primarySlot="video"
      fallbackSlot="videoFallback"
      health={health}
    />
  );
});

VideoFallbackCard.displayName = 'VideoFallbackCard';

export default VideoFallbackCard;
