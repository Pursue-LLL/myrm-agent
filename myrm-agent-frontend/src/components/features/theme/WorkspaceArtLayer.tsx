'use client';

import { useEffect, useRef, useState } from 'react';
import type { CompiledThemeArtLayer } from '@/theme-engine/schema';

interface WorkspaceArtLayerProps {
  art: CompiledThemeArtLayer;
}

const WorkspaceArtLayer = ({ art }: WorkspaceArtLayerProps) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoFailed, setVideoFailed] = useState(false);

  useEffect(() => {
    setVideoFailed(false);
  }, [art.mediaKind, art.mediaUrl, art.posterUrl]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || art.mediaKind !== 'video' || !art.mediaUrl || videoFailed) {
      return;
    }
    video.src = art.mediaUrl;
    const play = video.play();
    if (play) {
      play.catch(() => {
        setVideoFailed(true);
      });
    }
  }, [art.mediaKind, art.mediaUrl, videoFailed]);

  if (!art.enabled) {
    return null;
  }

  const showVideo = art.mediaKind === 'video' && Boolean(art.mediaUrl) && !videoFailed;
  const staticImageUrl = art.posterUrl ?? (showVideo ? null : art.mediaUrl);

  if (!showVideo && !staticImageUrl) {
    return null;
  }

  const backgroundPosition = `${art.focusX * 100}% ${art.focusY * 100}%`;
  const washOverlayStyle = {
    backgroundColor: `color-mix(in srgb, var(--background) ${Math.round(art.wash * 100)}%, transparent)`,
  };

  return (
    <div
      id="myrm-art-layer"
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      style={{
        backgroundColor: 'var(--background)',
      }}
    >
      {staticImageUrl && !showVideo ? (
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `url(${staticImageUrl})`,
            backgroundSize: 'cover',
            backgroundPosition,
            backgroundRepeat: 'no-repeat',
          }}
        />
      ) : null}
      {showVideo && art.mediaUrl ? (
        <video
          ref={videoRef}
          className="absolute inset-0 h-full w-full object-cover"
          style={{ objectPosition: backgroundPosition }}
          muted
          loop
          playsInline
          preload="metadata"
          poster={art.posterUrl ?? undefined}
          onError={() => setVideoFailed(true)}
        />
      ) : null}
      <div className="absolute inset-0 backdrop-blur-[1px]" style={washOverlayStyle} />
    </div>
  );
};

export default WorkspaceArtLayer;
