/**
 * [INPUT]
 * hooks/useCameraInput (POS: Camera input manager with frame buffering)
 *
 * [OUTPUT]
 * CameraInputButton: Toggle button for camera input with facing mode switch
 *
 * [POS]
 * Camera toggle UI control. Provides camera on/off and front/back facing switch for the input toolbar.
 */

'use client';

import { memo } from 'react';
import { Camera, CameraOff, SwitchCamera } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import Tooltip from '@/components/ui/settings/Tooltip';
import type { CameraState, FacingMode } from '@/hooks/useCameraInput';

interface CameraInputButtonProps {
  cameraState: CameraState;
  facingMode: FacingMode;
  onToggleCamera: () => void;
  onToggleFacing: () => void;
  disabled?: boolean;
}

const CameraInputButton = memo(
  ({ cameraState, facingMode, onToggleCamera, onToggleFacing, disabled = false }: CameraInputButtonProps) => {
    const t = useTranslations('camera');

    const isActive = cameraState === 'active';
    const isStarting = cameraState === 'starting';

    const tooltipText = isActive ? t('stopCamera') : isStarting ? t('starting') : t('startCamera');

    return (
      <div className="relative flex items-center gap-0.5">
        <Tooltip content={tooltipText}>
          <button
            type="button"
            onClick={onToggleCamera}
            disabled={disabled || isStarting}
            className={cn(
              'flex items-center justify-center rounded-full transition duration-200 w-8 h-8',
              isActive
                ? 'bg-blue-500/15 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 hover:bg-blue-500/25 dark:hover:bg-blue-500/30'
                : 'bg-[#fdfdf8] dark:bg-muted/60 hover:bg-[#e8e8e0] dark:hover:bg-muted/80 text-black/70 dark:text-white/70 hover:text-black dark:hover:text-white',
              (disabled || isStarting) && 'opacity-50 cursor-not-allowed',
            )}
            aria-label={tooltipText}
          >
            {isActive ? <CameraOff size={16} /> : <Camera size={16} />}
          </button>
        </Tooltip>
        {isActive && (
          <Tooltip content={facingMode === 'user' ? t('switchToBack') : t('switchToFront')}>
            <button
              type="button"
              onClick={onToggleFacing}
              className="flex items-center justify-center rounded-full w-6 h-6 bg-[#fdfdf8] dark:bg-muted/60 hover:bg-[#e8e8e0] dark:hover:bg-muted/80 text-black/70 dark:text-white/70 hover:text-black dark:hover:text-white transition duration-200"
              aria-label={facingMode === 'user' ? t('switchToBack') : t('switchToFront')}
            >
              <SwitchCamera size={12} />
            </button>
          </Tooltip>
        )}
      </div>
    );
  },
);

CameraInputButton.displayName = 'CameraInputButton';

export default CameraInputButton;
