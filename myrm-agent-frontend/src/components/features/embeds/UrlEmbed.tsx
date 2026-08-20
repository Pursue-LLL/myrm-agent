'use client';

import { type CSSProperties, lazy, Suspense, useState } from 'react';
import useEmbedConsentStore from '@/store/useEmbedConsentStore';
import { EmbedFacade } from './EmbedFacade';
import { EmbedFail } from './EmbedFail';
import { EmbedErrorBoundary } from './EmbedErrorBoundary';
import type { EmbedDescriptor } from './providers/types';

const EMBED_MAX_H = '400px';

const FrameEmbedRenderer = lazy(() => import('./FrameEmbedRenderer'));

function intrinsicHeight(descriptor: EmbedDescriptor): number {
  if (descriptor.aspectRatio) {
    return Math.round((descriptor.maxWidth ?? 640) / descriptor.aspectRatio);
  }
  return descriptor.height ?? 320;
}

function LazyRenderer({ descriptor }: { descriptor: EmbedDescriptor }) {
  if (descriptor.renderer === 'tweet') {
    return (
      <FrameEmbedRenderer
        descriptor={{
          ...descriptor,
          renderer: 'frame' as const,
          embedUrl: `https://platform.twitter.com/embed/Tweet.html?dnt=true&id=${descriptor.tweetId}&theme=light`,
          aspectRatio: undefined,
          height: 300,
        }}
      />
    );
  }

  return <FrameEmbedRenderer descriptor={descriptor} />;
}

export function UrlEmbed({ descriptor }: { descriptor: EmbedDescriptor }) {
  const embedMode = useEmbedConsentStore((s) => s.embedMode);
  const allowedProviders = useEmbedConsentStore((s) => s.allowedProviders);
  const [loaded, setLoaded] = useState(false);

  if (embedMode === 'off') {
    return (
      <a
        href={descriptor.sourceUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors"
      >
        {descriptor.sourceUrl}
      </a>
    );
  }

  const consented = embedMode === 'always' || loaded || allowedProviders.includes(descriptor.provider);
  const style: CSSProperties = {
    containIntrinsicSize: `auto ${intrinsicHeight(descriptor)}px`,
    contentVisibility: 'auto',
    ...(descriptor.aspectRatio
      ? { width: `min(${descriptor.maxWidth ?? 640}px, 100%, calc(${EMBED_MAX_H} * ${descriptor.aspectRatio}))` }
      : { width: descriptor.maxWidth ? `min(${descriptor.maxWidth}px, 100%)` : '100%' }),
  };

  return (
    <span className="group/embed my-2 block overflow-hidden rounded-lg" data-slot="embed-card" style={style}>
      <EmbedErrorBoundary fallback={<EmbedFail label={descriptor.label} />} resetKey={descriptor.id}>
        {consented ? (
          <Suspense fallback={null}>
            <LazyRenderer descriptor={descriptor} />
          </Suspense>
        ) : (
          <EmbedFacade descriptor={descriptor} onLoad={() => setLoaded(true)} />
        )}
      </EmbedErrorBoundary>
    </span>
  );
}
