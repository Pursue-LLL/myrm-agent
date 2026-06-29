'use client';

/**
 * PetGallery — Visual gallery for browsing and installing Petdex community pets.
 *
 * [INPUT]
 * - useCompanionStore (POS: Companion state with sprite config)
 *
 * [OUTPUT]
 * - PetGallery: Grid gallery with search, lazy-load thumbnails, one-click install
 *
 * [POS]
 * Fetches the public petdex.dev manifest (2900+ pets, ~500KB, unauthenticated)
 * and renders a searchable grid. Thumbnails use IntersectionObserver for lazy
 * loading; manifest is cached in sessionStorage + memory for 5 minutes.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import useCompanionStore from '@/store/useCompanionStore';

// ---------------------------------------------------------------------------
// Manifest types & cache
// ---------------------------------------------------------------------------

interface ManifestPet {
  slug: string;
  displayName: string;
  kind: string;
  spritesheetUrl: string;
}

const MANIFEST_URL = 'https://petdex.dev/api/manifest';
const CACHE_KEY = 'myrm-petdex-manifest';
const CACHE_TTL_MS = 300_000;

let memoryCache: { ts: number; pets: ManifestPet[] } | null = null;

async function fetchManifest(): Promise<ManifestPet[]> {
  if (memoryCache && Date.now() - memoryCache.ts < CACHE_TTL_MS) {
    return memoryCache.pets;
  }

  try {
    const cached = sessionStorage.getItem(CACHE_KEY);
    if (cached) {
      const parsed = JSON.parse(cached) as { ts: number; pets: ManifestPet[] };
      if (Date.now() - parsed.ts < CACHE_TTL_MS) {
        memoryCache = parsed;
        return parsed.pets;
      }
    }
  } catch {}

  const resp = await fetch(MANIFEST_URL);
  if (!resp.ok) throw new Error(`Manifest fetch failed: ${resp.status}`);

  const payload = await resp.json();
  const raw = payload?.pets;
  if (!Array.isArray(raw)) throw new Error('Invalid manifest format');

  const pets: ManifestPet[] = [];
  for (const entry of raw) {
    if (!entry?.slug || !entry?.spritesheetUrl) continue;
    pets.push({
      slug: String(entry.slug),
      displayName: String(entry.displayName || entry.slug),
      kind: String(entry.kind || 'pet'),
      spritesheetUrl: String(entry.spritesheetUrl),
    });
  }

  const cacheObj = { ts: Date.now(), pets };
  memoryCache = cacheObj;
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cacheObj));
  } catch {}

  return pets;
}

// ---------------------------------------------------------------------------
// Lazy thumbnail component
// ---------------------------------------------------------------------------

const THUMB_SIZE = 64;

function PetThumb({ url, alt }: { url: string; alt: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let pendingImg: HTMLImageElement | null = null;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || cancelled) return;
        observer.disconnect();

        const img = new Image();
        pendingImg = img;
        img.crossOrigin = 'anonymous';
        img.onload = () => {
          if (cancelled) return;
          const canvas = canvasRef.current;
          if (!canvas) return;
          const ctx = canvas.getContext('2d', { alpha: true });
          if (!ctx) return;
          ctx.imageSmoothingEnabled = false;
          const cellW = Math.min(192, img.naturalWidth);
          const cellH = Math.min(208, img.naturalHeight);
          canvas.width = THUMB_SIZE;
          canvas.height = THUMB_SIZE;
          ctx.drawImage(img, 0, 0, cellW, cellH, 0, 0, THUMB_SIZE, THUMB_SIZE);
          setLoaded(true);
        };
        img.src = url;
      },
      { rootMargin: '200px' },
    );
    observer.observe(container);
    return () => {
      cancelled = true;
      observer.disconnect();
      if (pendingImg) {
        pendingImg.onload = null;
        pendingImg.src = '';
      }
    };
  }, [url]);

  return (
    <div ref={containerRef} className="flex items-center justify-center" style={{ width: THUMB_SIZE, height: THUMB_SIZE }}>
      <canvas
        ref={canvasRef}
        className={cn('w-full h-full', !loaded && 'hidden')}
        style={{ imageRendering: 'pixelated' }}
        aria-label={alt}
      />
      {!loaded && (
        <div className="w-full h-full rounded-md bg-muted animate-pulse" />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grid constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 60;

// ---------------------------------------------------------------------------
// PetGallery
// ---------------------------------------------------------------------------

interface PetGalleryProps {
  onInstall?: () => void;
}

export default function PetGallery({ onInstall }: PetGalleryProps) {
  const t = useTranslations('companion');
  const setSpriteConfig = useCompanionStore((s) => s.setSpriteConfig);
  const setSpriteEnabled = useCompanionStore((s) => s.setSpriteEnabled);
  const saveConfigToServer = useCompanionStore((s) => s.saveConfigToServer);
  const currentSlug = useCompanionStore((s) => s.spriteConfig)?.name;

  const [pets, setPets] = useState<ManifestPet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchManifest()
      .then((data) => {
        if (!cancelled) setPets(data);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return pets;
    const q = search.trim().toLowerCase();
    return pets.filter(
      (p) => p.slug.toLowerCase().includes(q) || p.displayName.toLowerCase().includes(q),
    );
  }, [pets, search]);

  const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisibleCount((prev) => Math.min(prev + PAGE_SIZE, filtered.length));
      }
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [filtered.length]);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [search]);

  const handleInstall = useCallback(
    (pet: ManifestPet) => {
      setSpriteConfig({ sheetUrl: pet.spritesheetUrl, name: pet.slug });
      setSpriteEnabled(true);
      saveConfigToServer();
      onInstall?.();
    },
    [setSpriteConfig, setSpriteEnabled, saveConfigToServer, onInstall],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <span className="ml-2 text-sm text-muted-foreground">{t('gallery.loading')}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-6 text-center text-sm text-destructive">
        {t('gallery.error')}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={t('gallery.searchPlaceholder')}
        className="text-xs"
      />

      <div className="text-xs text-muted-foreground">
        {t('gallery.count', { count: filtered.length })}
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-[320px] overflow-y-auto pr-1">
        {visible.map((pet) => {
          const isActive = currentSlug === pet.slug;
          return (
            <button
              key={pet.slug}
              type="button"
              onClick={() => handleInstall(pet)}
              title={pet.displayName}
              className={cn(
                'flex flex-col items-center gap-1 rounded-lg p-1.5 transition-all',
                isActive
                  ? 'bg-primary/15 ring-1 ring-primary'
                  : 'hover:bg-muted',
              )}
            >
              <PetThumb url={pet.spritesheetUrl} alt={pet.displayName} />
              <span className="w-full truncate text-center text-[10px] leading-tight text-foreground">
                {pet.displayName}
              </span>
            </button>
          );
        })}
      </div>

      {visibleCount < filtered.length && (
        <div ref={sentinelRef} className="flex justify-center py-2">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
        </div>
      )}
    </div>
  );
}
