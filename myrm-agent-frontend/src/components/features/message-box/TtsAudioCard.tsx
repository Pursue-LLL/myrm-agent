'use client';

/**
 * [INPUT]
 * - PremiumIcons::IconHeadphones (POS: audio glyph consistent with artifact audio preview)
 *
 * [OUTPUT]
 * - TtsAudioCard: Inline playback card for tts_generate tool results.
 *
 * [POS]
 * Renders a successful tts_generate JSON payload (status=success + audio_url)
 * as an in-place audio player instead of raw JSON text.
 */

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconHeadphones } from '@/components/features/icons/PremiumIcons';

export interface TtsAudioCardProps {
  url: string;
  model?: string;
  durationSeconds?: number;
}

function TtsAudioCardImpl({ url, model, durationSeconds }: TtsAudioCardProps) {
  const t = useTranslations('ttsAudio');
  const [hasError, setHasError] = useState(false);

  const handleError = useCallback(() => setHasError(true), []);

  return (
    <div className="my-2 w-full max-w-md rounded-xl border border-border bg-background/80 p-3 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
          <IconHeadphones className="h-4 w-4 text-primary/80" />
        </span>
        <div className="min-w-0 flex-1">
          <span className="block text-xs font-medium text-foreground">{t('generatedSpeech')}</span>
          {(model || durationSeconds) && (
            <span className="block truncate text-[10px] text-muted-foreground">
              {model}
              {model && durationSeconds ? ' · ' : ''}
              {durationSeconds ? `${durationSeconds.toFixed(1)}s` : ''}
            </span>
          )}
        </div>
      </div>
      {hasError ? (
        <p className="text-xs text-red-500">{t('playbackFailed')}</p>
      ) : (
        <div className="rounded-full border border-border bg-muted/40 p-1.5">
          {/* Generated speech has no caption track file; a11y captions rule is not applicable. */}
          {/* oxlint-disable-next-line jsx-a11y/media-has-caption */}
          <audio
            src={url}
            controls
            preload="metadata"
            className="h-9 w-full outline-none"
            onError={handleError}
          />
        </div>
      )}
    </div>
  );
}

const TtsAudioCard = memo(TtsAudioCardImpl);
TtsAudioCard.displayName = 'TtsAudioCard';

export default TtsAudioCard;
