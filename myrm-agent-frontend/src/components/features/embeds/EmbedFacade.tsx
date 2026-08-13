'use client';

import { type CSSProperties, useState } from 'react';
import useEmbedConsentStore from '@/store/useEmbedConsentStore';
import type { EmbedDescriptor } from './providers/types';

function hostOf(descriptor: EmbedDescriptor): string {
  if (descriptor.provider === 'twitter') {return 'x.com';}
  try {
    return new URL(descriptor.sourceUrl).hostname.replace(/^www\./, '');
  } catch {
    return descriptor.label;
  }
}

export function EmbedFacade({ descriptor, onLoad }: { descriptor: EmbedDescriptor; onLoad: () => void }) {
  const allowProvider = useEmbedConsentStore((s) => s.allowProvider);
  const [showMenu, setShowMenu] = useState(false);

  const style: CSSProperties = descriptor.aspectRatio
    ? { aspectRatio: descriptor.aspectRatio }
    : { height: descriptor.height ?? 320 };

  return (
    <span
      className="flex size-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border/60 bg-accent/30"
      style={style}
    >
      <div className="flex items-center gap-2">
        <button
          onClick={onLoad}
          className="inline-flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition hover:bg-primary/20"
        >
          <svg className="h-3 w-3 translate-x-px fill-current" viewBox="0 0 16 16">
            <path d="M4 2l10 6-10 6z" />
          </svg>
          Load {descriptor.label}
        </button>
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="rounded-lg border border-border/60 bg-background px-2 py-2 text-xs text-muted-foreground transition hover:bg-accent"
            aria-label="More options"
          >
            <svg className="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4 8l4 4 4-4z" />
            </svg>
          </button>
          {showMenu && (
            <div className="absolute right-0 top-full z-10 mt-1 min-w-[180px] rounded-lg border border-border/60 bg-background p-1 shadow-lg">
              <button
                onClick={() => {
                  allowProvider(descriptor.provider);
                  onLoad();
                  setShowMenu(false);
                }}
                className="w-full rounded-md px-3 py-2 text-left text-sm text-foreground transition hover:bg-accent"
              >
                Always allow {descriptor.label}
              </button>
            </div>
          )}
        </div>
      </div>
      <span className="text-xs text-muted-foreground">{hostOf(descriptor)}</span>
    </span>
  );
}
