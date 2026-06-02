/**
 * [INPUT]
 * hooks/useCameraInput (POS: Camera input manager with frame buffering)
 *
 * [OUTPUT]
 * CameraPreview: Floating preview window showing camera feed above input bar
 *
 * [POS]
 * Camera preview overlay. Displays the live video feed in a compact window above the message input area.
 */

'use client';

import { memo } from 'react';
import { X } from 'lucide-react';
import type { CameraState } from '@/hooks/useCameraInput';
import { useTranslations } from 'next-intl';

interface CameraPreviewProps {
  cameraState: CameraState;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onClose: () => void;
  bufferSize?: number;
}

const CameraPreview = memo(({ cameraState, videoRef, onClose, bufferSize }: CameraPreviewProps) => {
  const t = useTranslations('camera');

  if (cameraState !== 'active' && cameraState !== 'starting') {
    return null;
  }

  return (
    <div className="relative mb-2 mx-3 rounded-xl overflow-hidden border border-border/50 bg-black/5 dark:bg-white/5">
      <div className="relative w-full aspect-video max-h-[160px]">
        <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover rounded-xl" />
        {cameraState === 'starting' && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/30 rounded-xl">
            <span className="text-xs text-white/80">{t('starting')}</span>
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="absolute top-1.5 right-1.5 p-1 rounded-full bg-black/40 hover:bg-black/60 text-white transition-colors"
        aria-label={t('stopCamera')}
      >
        <X size={12} />
      </button>
      {bufferSize !== undefined && bufferSize > 0 && (
        <div className="absolute bottom-1.5 left-1.5 px-1.5 py-0.5 rounded-full bg-black/40 text-[10px] text-white/80 tabular-nums">
          {bufferSize} {t('frames')}
        </div>
      )}
    </div>
  );
});

CameraPreview.displayName = 'CameraPreview';

export default CameraPreview;
