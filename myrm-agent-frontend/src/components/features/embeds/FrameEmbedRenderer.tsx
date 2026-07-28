'use client';

import type { FrameEmbed } from './providers/types';

const IFRAME_ALLOW = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen';

export default function FrameEmbedRenderer({ descriptor }: { descriptor: FrameEmbed }) {
  const style = descriptor.aspectRatio
    ? { aspectRatio: descriptor.aspectRatio }
    : { height: descriptor.height ?? 320 };

  return (
    <iframe
      allow={IFRAME_ALLOW}
      allowFullScreen
      className="block w-full border-0 bg-transparent"
      loading="lazy"
      referrerPolicy="strict-origin-when-cross-origin"
      sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      scrolling="no"
      src={descriptor.embedUrl}
      style={style}
      title={`${descriptor.label} embed`}
    />
  );
}
