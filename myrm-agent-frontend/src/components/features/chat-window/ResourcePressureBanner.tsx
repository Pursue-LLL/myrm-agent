'use client';

/**
 * [INPUT]
 * - /api/v1/health/pressure (POS: user-facing memory + disk pressure snapshot)
 *
 * [OUTPUT]
 * ResourcePressureBanner: worst-first resource pressure banner.
 *
 * [POS]
 * EmptyChat banner shown on resource trouble. Trigger priority mirrors the
 * Hermes design: disk-critical (silent data loss) outranks everything, then
 * memory-critical, then elevated warnings. Dismissals are session-scoped and
 * any escalation re-opens immediately; recovery clears them.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/primitives/button';
import { IconAlertCircle } from '@/components/features/icons/PremiumIcons';

type Trigger = 'disk_critical' | 'memory_critical' | 'disk_elevated' | 'memory_elevated';

const POLL_INTERVAL_MS = 60_000;
const DISMISS_KEY = 'resource_pressure_dismissed';

interface PressurePayload {
  memory?: { level?: string };
  disk?: { state?: string };
}

function pickTrigger(payload: PressurePayload): Trigger | null {
  const memoryLevel = (payload.memory?.level ?? 'unknown').toLowerCase();
  const diskState = (payload.disk?.state ?? 'unknown').toLowerCase();
  if (diskState === 'critical') {
    return 'disk_critical';
  }
  if (memoryLevel === 'critical' || memoryLevel === 'emergency') {
    return 'memory_critical';
  }
  if (diskState === 'elevated') {
    return 'disk_elevated';
  }
  if (memoryLevel === 'warning') {
    return 'memory_elevated';
  }
  return null;
}

function readDismissed(): string[] {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(DISMISS_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
  } catch {
    return [];
  }
}

function writeDismissed(triggers: string[]): void {
  try {
    sessionStorage.setItem(DISMISS_KEY, JSON.stringify(triggers));
  } catch {
    // Best effort only.
  }
}

const TRIGGER_SEVERITY: Record<Trigger, number> = {
  disk_critical: 4,
  memory_critical: 3,
  disk_elevated: 2,
  memory_elevated: 1,
};

export default function ResourcePressureBanner() {
  const t = useTranslations('chat.pressureBanner');
  const router = useRouter();
  const [trigger, setTrigger] = useState<Trigger | null>(null);

  useEffect(() => {
    let cancelled = false;

    const probe = async () => {
      try {
        const response = await fetch('/api/v1/health/pressure');
        if (!response.ok || cancelled) {
          return;
        }
        const payload = (await response.json()) as PressurePayload;
        if (cancelled) {
          return;
        }
        const next = pickTrigger(payload);
        if (next === null) {
          // Confirmed recovery clears live dismissals for the next episode.
          writeDismissed([]);
          setTrigger(null);
          return;
        }
        const dismissed = readDismissed();
        if (dismissed.includes(next)) {
          setTrigger((current) => {
            // Escalation re-opens even mid-dismissal: compare severity.
            if (current && TRIGGER_SEVERITY[next] > TRIGGER_SEVERITY[current]) {
              return next;
            }
            return current;
          });
          return;
        }
        setTrigger(next);
      } catch {
        // Pressure service unreachable — stay silent, never block chat.
      }
    };

    void probe();
    const timer = setInterval(() => {
      void probe();
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const handleOpen = useCallback(() => {
    router.push('/settings/system?sub=about');
  }, [router]);

  const handleDismiss = useCallback(() => {
    setTrigger((current) => {
      if (current) {
        writeDismissed([...readDismissed(), current]);
      }
      return null;
    });
  }, []);

  if (!trigger) {
    return null;
  }

  return (
    <div
      className="flex items-center gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4"
      role="alert"
    >
      <IconAlertCircle className="w-5 h-5 shrink-0 text-destructive" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-foreground">{t(`trigger.${trigger}.title`)}</p>
        <p className="text-xs text-muted-foreground leading-relaxed">{t(`trigger.${trigger}.description`)}</p>
      </div>
      <Button size="sm" onClick={handleOpen} className="gap-1 shrink-0">
        {t('open')}
      </Button>
      <button
        type="button"
        onClick={handleDismiss}
        aria-label={t('dismiss')}
        className="shrink-0 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {t('dismiss')}
      </button>
    </div>
  );
}
