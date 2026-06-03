'use client';

import { memo, useCallback } from 'react';
import { Mic, MicOff, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/useToast';
import { useSpeechInput, type SpeechMode } from '@/hooks/useSpeechInput';
import Tooltip from '@/components/features/settings/Tooltip';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

const WAVEFORM_BARS = 5;

function VolumeWaveform({ level }: { level: number }) {
  const heights = Array.from({ length: WAVEFORM_BARS }, (_, i) => {
    const center = (WAVEFORM_BARS - 1) / 2;
    const dist = Math.abs(i - center) / center;
    const base = 0.2;
    const scale = Math.max(base, level * (1 - dist * 0.5));
    return Math.min(1, scale);
  });

  return (
    <div className="flex items-center gap-[2px] h-3.5">
      {heights.map((h, i) => (
        <span
          key={i}
          className="w-[2px] rounded-full bg-red-500 transition-[height] duration-75"
          style={{ height: `${Math.max(15, h * 100)}%` }}
        />
      ))}
    </div>
  );
}

interface SpeechInputButtonProps {
  onTranscript: (text: string) => void;
  onInterimTranscript?: (text: string) => void;
  disabled?: boolean;
  mode?: SpeechMode;
  enableSounds?: boolean;
  keyterms?: string[];
}

const SpeechInputButton = memo(
  ({
    onTranscript,
    onInterimTranscript,
    disabled = false,
    mode = 'toggle',
    enableSounds = false,
    keyterms,
  }: SpeechInputButtonProps) => {
    const t = useTranslations('stt');

    const handleError = useCallback(
      (msg: string) => {
        if (msg === 'tooShort') {
          toast({ title: t('error'), description: t('tooShort') });
        } else {
          toast({ title: t('error'), description: msg });
        }
      },
      [t],
    );

    const { state, elapsed, audioLevel, interimText, toggle, onPointerDown, onPointerUp, isSupported } = useSpeechInput(
      {
        onTranscript,
        onInterimTranscript,
        onError: handleError,
        mode,
        enableSounds,
        keyterms,
      },
    );

    if (!isSupported) return null;

    const isRecording = state === 'recording';
    const isTranscribing = state === 'transcribing';
    const isPushToTalk = mode === 'push-to-talk';

    const tooltipText = isRecording
      ? isPushToTalk
        ? t('releaseToStop')
        : t('stopRecording')
      : isTranscribing
        ? t('transcribing')
        : isPushToTalk
          ? t('holdToTalk')
          : t('startRecording');

    return (
      <div className="relative flex items-center">
        <Tooltip content={tooltipText}>
          <button
            type="button"
            onClick={isPushToTalk ? undefined : toggle}
            onPointerDown={isPushToTalk ? onPointerDown : undefined}
            onPointerUp={isPushToTalk ? onPointerUp : undefined}
            onPointerLeave={isPushToTalk && isRecording ? onPointerUp : undefined}
            disabled={disabled || isTranscribing}
            className={cn(
              'relative flex items-center justify-center rounded-full transition duration-200 select-none',
              isRecording
                ? 'h-8 gap-1.5 px-2.5 bg-red-500/15 dark:bg-red-500/20 text-red-600 dark:text-red-400 hover:bg-red-500/25 dark:hover:bg-red-500/30'
                : 'w-8 h-8 bg-[#fdfdf8] dark:bg-muted/60 hover:bg-[#e8e8e0] dark:hover:bg-muted/80 text-black/70 dark:text-white/70 hover:text-black dark:hover:text-white',
              (disabled || isTranscribing) && 'opacity-50 cursor-not-allowed',
            )}
            aria-label={tooltipText}
          >
            {isRecording && <VolumeWaveform level={audioLevel} />}

            {isTranscribing ? (
              <Loader2 size={16} className="animate-spin" />
            ) : isRecording ? (
              <MicOff size={14} />
            ) : (
              <Mic size={16} />
            )}

            {isRecording && <span className="text-xs tabular-nums font-medium">{formatTime(elapsed)}</span>}
          </button>
        </Tooltip>
        {isRecording && interimText && (
          <span className="ml-2 text-xs text-muted-foreground/60 max-w-[180px] truncate pointer-events-none animate-pulse">
            {interimText}
          </span>
        )}
      </div>
    );
  },
);

SpeechInputButton.displayName = 'SpeechInputButton';

export default SpeechInputButton;
