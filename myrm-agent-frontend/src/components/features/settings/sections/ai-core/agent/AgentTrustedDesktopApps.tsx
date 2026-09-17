'use client';

import { memo, useCallback, useEffect, useId, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest } from '@/lib/api';
import type { TrustedDesktopAppEntry } from '@/services/agent';

type TrustedAppSuggestion = {
  trust_key: string;
  display_name: string;
  app_id: string;
};

type Props = {
  apps: TrustedDesktopAppEntry[];
  onChange: (apps: TrustedDesktopAppEntry[]) => void;
  readonly?: boolean;
};

function AgentTrustedDesktopAppsInner({ apps, onChange, readonly }: Props) {
  const t = useTranslations('agent');
  const inputId = useId();
  const [draft, setDraft] = useState('');
  const [suggestions, setSuggestions] = useState<TrustedAppSuggestion[]>([]);

  useEffect(() => {
    let cancelled = false;
    apiRequest<{ apps: TrustedAppSuggestion[] }>('/webui/desktop/trust/apps', { silent: true })
      .then((data) => {
        if (!cancelled) {
          setSuggestions(data.apps ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSuggestions([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const addDraft = useCallback(() => {
    const name = draft.trim();
    if (!name || readonly) {
      return;
    }
    if (apps.some((app) => app.name === name)) {
      setDraft('');
      return;
    }
    const match = suggestions.find((s) => s.display_name === name);
    const entry: TrustedDesktopAppEntry = match?.app_id
      ? { name, app_id: match.app_id }
      : { name };
    onChange([...apps, entry]);
    setDraft('');
  }, [apps, draft, onChange, readonly, suggestions]);

  const removeAt = useCallback(
    (index: number) => {
      if (readonly) {
        return;
      }
      onChange(apps.filter((_, i) => i !== index));
    },
    [apps, onChange, readonly],
  );

  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4">
      <div className="mb-3">
        <h4 className="text-sm font-medium text-foreground">{t('trustedDesktopApps')}</h4>
        <p className="text-xs text-muted-foreground mt-0.5">{t('trustedDesktopAppsDesc')}</p>
        <p className="text-[11px] text-muted-foreground/80 mt-1.5 leading-relaxed">
          {t('trustedDesktopAppsHint')}
        </p>
      </div>
      {apps.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {apps.map((app, index) => (
            <span
              key={`${app.name}-${index}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border/50 bg-secondary/30 px-2.5 py-1 text-xs text-foreground"
            >
              {app.name}
              {!readonly && (
                <button
                  type="button"
                  onClick={() => removeAt(index)}
                  aria-label={t('trustedDesktopAppsRemove', { name: app.name })}
                  className="text-muted-foreground hover:text-foreground transition-colors"
                >
                  ×
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {!readonly && (
        <div className="flex gap-2">
          <input
            id={inputId}
            aria-label={t('trustedDesktopApps')}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addDraft();
              }
            }}
            list={`${inputId}-suggestions`}
            placeholder={t('trustedDesktopAppsPlaceholder')}
            className={cn(
              'flex-1 min-w-0 rounded-lg border border-border/50 bg-secondary/30',
              'px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60',
              'focus:outline-none focus:border-primary/60',
            )}
          />
          <datalist id={`${inputId}-suggestions`}>
            {suggestions.map((s) => (
              <option key={s.trust_key} value={s.display_name}>
                {s.display_name}
              </option>
            ))}
          </datalist>
          <button
            type="button"
            onClick={addDraft}
            disabled={!draft.trim()}
            className={cn(
              'shrink-0 rounded-lg px-3 py-2 text-xs font-medium transition-colors border',
              draft.trim()
                ? 'border-primary bg-primary/10 text-primary hover:bg-primary/20'
                : 'border-border/50 bg-secondary/30 text-muted-foreground/50 cursor-not-allowed',
            )}
          >
            {t('trustedDesktopAppsAdd')}
          </button>
        </div>
      )}
    </div>
  );
}

export const AgentTrustedDesktopApps = memo(AgentTrustedDesktopAppsInner);
