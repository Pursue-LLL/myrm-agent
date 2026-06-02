/**
 * [INPUT]
 * store/useProviderStore (POS: Provider and model configuration state)
 *
 * [OUTPUT]
 * VisionCapabilityNotice: Warning banner when camera is active but model lacks vision support
 *
 * [POS]
 * Vision capability warning. Alerts users when camera input will be ineffective due to model limitations.
 */

'use client';

import { memo, useMemo } from 'react';
import { AlertCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useProviderStore from '@/store/useProviderStore';

interface VisionCapabilityNoticeProps {
  cameraActive: boolean;
}

const VisionCapabilityNotice = memo(({ cameraActive }: VisionCapabilityNoticeProps) => {
  const t = useTranslations('camera');
  const defaultModelConfig = useProviderStore((s) => s.defaultModelConfig);
  const getModelInfo = useProviderStore((s) => s.getModelInfo);

  const supportsVision = useMemo(() => {
    const selection = defaultModelConfig?.baseModel?.primary;
    if (!selection) return false;
    return getModelInfo(selection.providerId, selection.model)?.supports_vision ?? false;
  }, [defaultModelConfig, getModelInfo]);

  if (!cameraActive || supportsVision) return null;

  const modelName = defaultModelConfig?.baseModel?.primary?.model ?? '';

  return (
    <div className="mx-3 mb-2 flex items-start gap-2 rounded-2xl border border-amber-200/80 bg-amber-50/90 dark:border-amber-700/50 dark:bg-amber-950/30 px-3 py-2 text-[11px] leading-5 text-amber-800 dark:text-amber-300">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
      <span>{modelName ? t('noVisionModelWithName', { model: modelName }) : t('noVisionModel')}</span>
    </div>
  );
});

VisionCapabilityNotice.displayName = 'VisionCapabilityNotice';

export default VisionCapabilityNotice;
