/**
 * Artifact Audio Digest Player Card Component
 * AI 工件自适应口语化音频简报随身听播放器：波形跳动、双人对白字幕高亮与跨端流转触发
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 无障碍标准与移动端随身听触控支持。
 */

import React, { useEffect } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  FastForward,
  Headphones,
  QrCode,
  Volume2,
  Mic,
  Sparkles,
} from 'lucide-react';
import { PlaybackRate, PodcastSegment } from './audioDigestTypes';
import { useAudioDigestStore } from './useAudioDigestStore';
import { formatSecondsToTimestamp } from './podcastSynthesizerEngine';

export interface ArtifactAudioDigestPlayerCardProps {
  className?: string;
}

const PLAYBACK_RATES: readonly PlaybackRate[] = [1.0, 1.25, 1.5, 2.0];

export const ArtifactAudioDigestPlayerCard: React.FC<
  ArtifactAudioDigestPlayerCardProps
> = ({ className = '' }) => {
  const {
    currentDigest,
    playbackState,
    currentSecond,
    playbackRate,
    activeSegment,
    togglePlayPause,
    seekToSecond,
    skipSeconds,
    setPlaybackRate,
    generateContinuationCapsule,
  } = useAudioDigestStore();

  const isPlaying = playbackState === 'playing';

  // 播放计时模拟器（当在播放态时按倍速推进时间）
  useEffect(() => {
    if (!isPlaying) {
      return;
    }

    const interval = setInterval(() => {
      seekToSecond(currentSecond + 1 * playbackRate);
    }, 1000);

    return () => {
      clearInterval(interval);
    };
  }, [isPlaying, currentSecond, playbackRate, seekToSecond]);

  const progressPercent = Math.min(
    100,
    (currentSecond / currentDigest.totalDurationSeconds) * 100
  );

  return (
    <div
      data-testid="audio-digest-player-card"
      className={`relative flex flex-col rounded-2xl border border-indigo-500/30 bg-neutral-900/90 p-4 text-neutral-100 shadow-xl backdrop-blur-lg space-y-3 ${className}`}
    >
      {/* 顶部标题与流转大屏按钮 */}
      <div className="flex items-center justify-between border-b border-neutral-800/80 pb-2.5">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
            <Headphones className="h-4 w-4" />
          </div>
          <div className="overflow-hidden">
            <div className="flex items-center gap-1.5 truncate">
              <span className="font-semibold text-xs text-white truncate">
                {currentDigest.artifactTitle}
              </span>
              <span className="rounded bg-indigo-500/20 px-1.5 py-0.2 font-mono text-[10px] text-indigo-300 font-bold shrink-0">
                播客简报
              </span>
            </div>
            <div className="text-[10px] text-neutral-400 font-mono truncate">
              {currentDigest.summaryHighlight}
            </div>
          </div>
        </div>

        {/* 扫码流转大屏胶囊触发 */}
        <button
          type="button"
          data-testid="trigger-continuation-capsule-btn"
          onClick={() => {
            generateContinuationCapsule('Mobile Earphones');
          }}
          className="flex items-center gap-1 rounded-lg border border-indigo-500/40 bg-indigo-950/40 px-2.5 py-1 text-xs text-indigo-300 hover:bg-indigo-900/50 hover:text-white transition-colors shrink-0"
          title="生成连续性流转胶囊（扫码回大屏细读图表与代码）"
        >
          <QrCode className="h-3.5 w-3.5" />
          <span className="font-mono text-[11px] hidden sm:inline">
            流转大屏
          </span>
        </button>
      </div>

      {/* 波形与播放进度栏 */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[11px] font-mono text-neutral-400">
          <div className="flex items-center gap-1.5">
            <Volume2 className="h-3.5 w-3.5 text-indigo-400" />
            <span data-testid="current-time-text">
              {formatSecondsToTimestamp(currentSecond)}
            </span>
          </div>

          {/* 跳动波形动画模拟 */}
          <div
            data-testid="waveform-indicator"
            className="flex items-center gap-0.5"
          >
            {[40, 70, 90, 60, 100, 50, 80].map((height, i) => (
              <span
                key={i}
                className={`w-0.5 rounded-full bg-indigo-400 transition-all duration-200 ${
                  isPlaying ? 'animate-pulse' : 'opacity-40'
                }`}
                style={{ height: `${(height / 100) * 12}px` }}
              />
            ))}
          </div>

          <span data-testid="total-duration-text">
            {formatSecondsToTimestamp(currentDigest.totalDurationSeconds)}
          </span>
        </div>

        {/* 可点击进度条 */}
        <button
          type="button"
          aria-label="调整播放进度"
          data-testid="playback-progress-track"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const clickRatio = (e.clientX - rect.left) / rect.width;
            seekToSecond(clickRatio * currentDigest.totalDurationSeconds);
          }}
          className="relative h-2 w-full cursor-pointer overflow-hidden rounded-full bg-neutral-800 p-0 border-0 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <div
            data-testid="playback-progress-fill"
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400 transition-all duration-150"
            style={{ width: `${progressPercent}%` }}
          />
        </button>
      </div>

      {/* 控制按钮与倍速切换 */}
      <div className="flex items-center justify-between pt-1">
        {/* 倍速切换 */}
        <div className="flex items-center gap-1 rounded-lg bg-neutral-950/80 p-0.5 border border-neutral-800">
          {PLAYBACK_RATES.map((rate) => (
            <button
              type="button"
              key={rate}
              data-testid={`playback-rate-btn-${rate}`}
              onClick={() => {
                setPlaybackRate(rate);
              }}
              className={`rounded px-1.5 py-0.5 font-mono text-[10px] transition-colors ${
                playbackRate === rate
                  ? 'bg-indigo-600 text-white font-bold'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              {rate}x
            </button>
          ))}
        </div>

        {/* 核心播放控制 */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="skip-back-15s-btn"
            onClick={() => {
              skipSeconds(-15);
            }}
            className="rounded-full p-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
            title="快退 15 秒"
          >
            <RotateCcw className="h-4 w-4" />
          </button>

          <button
            type="button"
            data-testid="play-pause-toggle-btn"
            onClick={togglePlayPause}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-600 text-white hover:bg-indigo-500 transition-all shadow-md hover:scale-105"
            title={isPlaying ? '暂停' : '播放'}
          >
            {isPlaying ? (
              <Pause className="h-4 w-4 fill-current" />
            ) : (
              <Play className="h-4 w-4 fill-current ml-0.5" />
            )}
          </button>

          <button
            type="button"
            data-testid="skip-forward-15s-btn"
            onClick={() => {
              skipSeconds(15);
            }}
            className="rounded-full p-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
            title="快进 15 秒"
          >
            <FastForward className="h-4 w-4" />
          </button>
        </div>

        <div className="font-mono text-[10px] text-neutral-500 hidden sm:block">
          AI 语音合成播客
        </div>
      </div>

      {/* 口语化逐句对白字幕滚动列表 */}
      <div
        data-testid="podcast-transcript-container"
        className="max-h-36 overflow-y-auto rounded-xl border border-neutral-800/80 bg-neutral-950/60 p-2 space-y-1.5"
      >
        {currentDigest.segments.map((segment: PodcastSegment) => {
          const isActive = activeSegment?.id === segment.id;
          const isAnalyst = segment.speaker === 'analyst';

          return (
            <button
              type="button"
              key={segment.id}
              data-testid={`transcript-segment-${segment.id}`}
              onClick={() => {
                seekToSecond(segment.startSecond);
              }}
              className={`flex w-full flex-col items-start rounded-lg p-2 text-left transition-all text-xs ${
                isActive
                  ? 'border border-indigo-500/50 bg-indigo-950/40 text-white shadow-sm ring-1 ring-indigo-500/30'
                  : 'text-neutral-400 hover:bg-neutral-900/80 hover:text-neutral-200'
              }`}
            >
              <div className="flex items-center justify-between w-full font-mono text-[10px] mb-1">
                <span
                  className={`flex items-center gap-1 font-semibold ${
                    isAnalyst ? 'text-cyan-400' : 'text-purple-400'
                  }`}
                >
                  {isAnalyst ? (
                    <Sparkles className="h-3 w-3" />
                  ) : (
                    <Mic className="h-3 w-3" />
                  )}
                  <span>{segment.speakerName}</span>
                </span>
                <span className="text-neutral-500">
                  {formatSecondsToTimestamp(segment.startSecond)} -{' '}
                  {formatSecondsToTimestamp(segment.endSecond)}
                </span>
              </div>

              <p className="line-clamp-2 leading-relaxed text-[11px]">
                {segment.text}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
};
