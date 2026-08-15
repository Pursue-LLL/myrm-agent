'use client';

/**
 * Replay controls header: title, seek-to-error, playback speed, play/pause,
 * scrubber timeline with event markers, and the current-position readout.
 */

import { useTranslations } from 'next-intl';
import { IconAlertTriangle, IconPlay, IconStop } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import type { ReplayEventMarker } from '@/components/features/memory/replay/replayTimeline';

interface ReplayControlsProps {
  activeIndex: number;
  timelineLength: number;
  currentTime: number;
  startTime: number;
  endTime: number;
  totalDuration: number;
  progressPercent: number;
  isPlaying: boolean;
  isScrubbing: boolean;
  playbackSpeed: number;
  errorCount: number;
  eventMarkers: ReplayEventMarker[];
  onTogglePlay: () => void;
  onSeekToError: () => void;
  onSpeedChange: (speed: number) => void;
  onScrubChange: (time: number) => void;
  onScrubEnd: (time: number) => void;
}

const MARKER_COLORS: Record<ReplayEventMarker['kind'], string> = {
  tool: 'bg-amber-500',
  llm: 'bg-violet-500',
  message: 'bg-blue-500',
  memory: 'bg-teal-500',
  error: 'bg-rose-500',
};

function ReplayControls({
  activeIndex,
  timelineLength,
  currentTime,
  startTime,
  endTime,
  totalDuration,
  progressPercent,
  isPlaying,
  isScrubbing,
  playbackSpeed,
  errorCount,
  eventMarkers,
  onTogglePlay,
  onSeekToError,
  onSpeedChange,
  onScrubChange,
  onScrubEnd,
}: ReplayControlsProps) {
  const t = useTranslations('settings.sessionAnalytics.replay');

  return (
    <div className="p-3 sm:p-4 border-b border-border/40 bg-muted/10 flex flex-col gap-3">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">{t('title')}</h3>
          <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-full uppercase tracking-wide">
            v2
          </span>
          {activeIndex >= 0 && (
            <span className="text-[10px] text-muted-foreground font-mono">
              {activeIndex + 1}/{timelineLength}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={onSeekToError}
            disabled={errorCount === 0}
            className="text-xs text-rose-500 hover:bg-rose-500/10 disabled:opacity-40 disabled:pointer-events-none px-2 py-1 rounded transition-colors flex items-center gap-1"
          >
            <IconAlertTriangle className="w-3 h-3" />
            {t('seekToError')}
          </button>
          <select
            value={playbackSpeed}
            onChange={(e) => onSpeedChange(Number(e.target.value))}
            className="bg-muted/50 text-xs text-foreground border border-border/40 rounded-full px-2 py-1 outline-none focus:ring-1 focus:ring-blue-500/40 cursor-pointer"
            aria-label={t('speed')}
          >
            <option value={0.5}>0.5x</option>
            <option value={1}>1.0x</option>
            <option value={2}>2.0x</option>
            <option value={4}>4.0x</option>
          </select>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={onTogglePlay}
          className="p-2 hover:bg-muted/50 rounded-full transition-colors text-foreground shrink-0"
          aria-label={isPlaying ? t('pause') : t('play')}
        >
          {isPlaying ? <IconStop className="w-4 h-4" /> : <IconPlay className="w-4 h-4" />}
        </button>

        <div className="flex-1 relative h-8 flex items-center">
          <div className="absolute inset-x-0 flex items-center">
            <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden relative">
              <div className="h-full bg-blue-500 transition-none" style={{ width: `${progressPercent}%` }} />
              {eventMarkers.map((marker, i) => (
                <div
                  key={`marker-${marker.kind}-${i}`}
                  className={cn(
                    'absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full border border-background',
                    MARKER_COLORS[marker.kind],
                  )}
                  style={{ left: `${Math.max(0, Math.min(100, marker.percent))}%` }}
                  title={t(`marker.${marker.kind}`)}
                />
              ))}
            </div>
          </div>
          <input
            type="range"
            min={startTime}
            max={endTime}
            value={currentTime}
            onChange={(e) => onScrubChange(Number(e.target.value))}
            onMouseUp={(e) => onScrubEnd(Number((e.target as HTMLInputElement).value))}
            onTouchEnd={(e) => {
              const target = e.target as HTMLInputElement;
              onScrubEnd(Number(target.value));
            }}
            className="absolute inset-0 w-full opacity-0 cursor-pointer h-full"
            aria-label={t('scrubber')}
          />
        </div>

        <div className="text-[10px] sm:text-xs font-mono text-muted-foreground w-16 sm:w-20 text-right shrink-0">
          {((currentTime - startTime) / 1000).toFixed(1)}s / {(totalDuration / 1000).toFixed(1)}s
        </div>
      </div>

      <p className="text-[10px] text-muted-foreground hidden sm:block">
        {isScrubbing ? t('scrubSnapHint') : t('keyboardHint')}
      </p>
    </div>
  );
}

export default ReplayControls;
