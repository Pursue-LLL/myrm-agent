'use client';

import { useEffect, useState } from 'react';

interface OgData {
  title?: string;
  description?: string;
  image?: string;
  site_name?: string;
  favicon?: string;
  url?: string;
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '…' : text;
}

export function OgCard({ url }: { url: string }) {
  const [og, setOg] = useState<OgData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fetchOg = async () => {
      try {
        const resp = await fetch(`/api/webui/og-metadata?url=${encodeURIComponent(url)}`);
        if (!resp.ok) {
          setFailed(true);
          return;
        }
        const data = await resp.json();
        if (!cancelled) {
          if (!data.title && !data.description && !data.image) {
            setFailed(true);
          } else {
            setOg(data);
          }
        }
      } catch {
        if (!cancelled) {
          setFailed(true);
        }
      }
    };
    fetchOg();
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (failed || !og) {
    return null;
  }

  const hostname = (() => {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch {
      return url;
    }
  })();

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="my-2 flex overflow-hidden rounded-lg border border-border/60 bg-card transition hover:border-primary/30 hover:shadow-sm"
      style={{ maxWidth: 540 }}
    >
      {og.image && (
        <div className="hidden w-[120px] flex-shrink-0 sm:block">
          <img
            src={og.image}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-1 p-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {og.favicon && (
            <img
              src={og.favicon}
              alt=""
              className="h-3.5 w-3.5 rounded-sm"
              loading="lazy"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
              }}
            />
          )}
          <span>{og.site_name || hostname}</span>
        </div>
        {og.title && (
          <p className="text-sm font-medium leading-snug text-foreground line-clamp-2">{truncate(og.title, 100)}</p>
        )}
        {og.description && (
          <p className="text-xs leading-relaxed text-muted-foreground line-clamp-2">{truncate(og.description, 160)}</p>
        )}
      </div>
    </a>
  );
}
