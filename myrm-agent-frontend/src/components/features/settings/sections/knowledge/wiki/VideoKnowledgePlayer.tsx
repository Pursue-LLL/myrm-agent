'use client';

import { useMemo, useState, useRef, useEffect } from 'react';
import { IconPlay, IconVideo } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';

export interface VideoTimestampChapter {
  startSeconds: number;
  endSeconds: number;
  label: string;
}

interface VideoKnowledgePlayerProps {
  sourceUrl: string;
  title?: string;
  chapters?: VideoTimestampChapter[];
  initialSeconds?: number;
  onTimeUpdate?: (seconds: number) => void;
  className?: string;
}

export function formatPlayerTime(seconds: number): string {
  const secInt = Math.max(0, Math.round(seconds));
  const h = Math.floor(secInt / 3600);
  const m = Math.floor((secInt % 3600) / 60);
  const s = secInt % 60;
  if (h > 0) {
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export function extractVideoEmbedInfo(url: string, seekSeconds: number = 0): {
  type: 'bilibili' | 'youtube' | 'direct';
  embedUrl: string;
  sourceId: string;
} {
  const trimmed = url.trim();

  // Bilibili match
  const biliMatch = trimmed.match(/bilibili\.com\/video\/(BV[a-zA-Z0-9]{10}|av\d+)/i);
  if (biliMatch) {
    const bvid = biliMatch[1];
    const embedUrl = `//player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1&danmaku=0&t=${Math.floor(seekSeconds)}`;
    return { type: 'bilibili', embedUrl, sourceId: bvid };
  }

  // YouTube match
  const ytMatch = trimmed.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/i);
  if (ytMatch) {
    const videoId = ytMatch[1];
    const embedUrl = `https://www.youtube-nocookie.com/embed/${videoId}?start=${Math.floor(seekSeconds)}&autoplay=1`;
    return { type: 'youtube', embedUrl, sourceId: videoId };
  }

  return { type: 'direct', embedUrl: trimmed, sourceId: trimmed };
}

export function VideoKnowledgePlayer({
  sourceUrl,
  title,
  chapters = [],
  initialSeconds = 0,
  onTimeUpdate,
  className = '',
}: VideoKnowledgePlayerProps) {
  const [currentSeconds, setCurrentSeconds] = useState(initialSeconds);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const embedInfo = useMemo(() => {
    return extractVideoEmbedInfo(sourceUrl, currentSeconds);
  }, [sourceUrl, currentSeconds]);

  const handleSeek = (sec: number) => {
    setCurrentSeconds(sec);
    if (embedInfo.type === 'direct' && videoRef.current) {
      videoRef.current.currentTime = sec;
      videoRef.current.play().catch(() => {});
    }
    if (onTimeUpdate) {
      onTimeUpdate(sec);
    }
  };

  useEffect(() => {
    if (initialSeconds > 0) {
      setCurrentSeconds(initialSeconds);
    }
  }, [initialSeconds]);

  return (
    <div className={`flex flex-col gap-3 rounded-xl border border-border/60 bg-card p-4 shadow-sm ${className}`}>
      <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <IconVideo className="h-4 w-4" />
          </div>
          <span className="text-sm font-medium tracking-tight text-foreground truncate max-w-md">
            {title || sourceUrl}
          </span>
        </div>
        <div className="text-xs text-muted-foreground font-mono">
          {formatPlayerTime(currentSeconds)}
        </div>
      </div>

      <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-black/90 shadow-inner">
        {embedInfo.type === 'direct' ? (
          <video
            ref={videoRef}
            src={embedInfo.embedUrl}
            controls
            className="h-full w-full object-contain"
            onTimeUpdate={(e) => {
              const sec = e.currentTarget.currentTime;
              setCurrentSeconds(sec);
              if (onTimeUpdate) {
                onTimeUpdate(sec);
              }
            }}
          />
        ) : (
          <iframe
            key={`${embedInfo.embedUrl}-${Math.floor(currentSeconds)}`}
            src={embedInfo.embedUrl}
            className="h-full w-full border-0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        )}
      </div>

      {chapters.length > 0 && (
        <div className="flex flex-col gap-1.5 pt-1">
          <div className="text-xs font-medium text-muted-foreground">
            时间戳快速导航
          </div>
          <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto pr-1">
            {chapters.map((ch, idx) => {
              const isActive =
                currentSeconds >= ch.startSeconds && currentSeconds <= ch.endSeconds;
              return (
                <Button
                  key={`${ch.startSeconds}-${idx}`}
                  variant={isActive ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleSeek(ch.startSeconds)}
                  className="h-7 px-2.5 text-xs font-mono flex items-center gap-1.5 transition-colors"
                >
                  <IconPlay className="h-3 w-3" />
                  <span>{formatPlayerTime(ch.startSeconds)}</span>
                  {ch.label && <span className="font-sans truncate max-w-28 text-[11px] opacity-80">{ch.label}</span>}
                </Button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
