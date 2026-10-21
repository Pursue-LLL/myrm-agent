'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';

import type { AgentReadinessItem } from '@/services/agent';

/** A finding can list dozens of servers or keys; a row names the first few and signals there are more. */
const MAX_NAMES_SHOWN = 3;

function summarizeNames(names: string[]): string {
  const shown = names.slice(0, MAX_NAMES_SHOWN).join(', ');
  return names.length > MAX_NAMES_SHOWN ? `${shown}…` : shown;
}

export interface ReadinessText {
  /** The dimension a finding belongs to, e.g. "Model". */
  label: (item: AgentReadinessItem) => string;
  /** What is wrong, in the user's language. */
  reason: (item: AgentReadinessItem) => string;
  /** The call to action on an item that needs attention. */
  fix: string;
}

/**
 * Localized words for readiness findings.
 *
 * The backend's English `reason` / `next_action` are diagnostics and are never shown: findings speak
 * through their stable `code`, and a code or dimension this build does not know reads as a generic
 * line instead of leaking the diagnostic.
 */
export function useReadinessText(): ReadinessText {
  const t = useTranslations('Agent.readiness');

  return useMemo(() => {
    const has = (key: string) => t.has(key as Parameters<typeof t.has>[0]);
    const translate = (key: string, values?: Record<string, string | number>) =>
      t(key as Parameters<typeof t>[0], values);

    return {
      label: (item) =>
        has(`dimensions.${item.dimension}`) ? translate(`dimensions.${item.dimension}`) : translate('dimensions.other'),
      reason: (item) =>
        has(`reasons.${item.code}`)
          ? translate(`reasons.${item.code}`, { names: summarizeNames(item.names), count: item.count })
          : translate(`fallback.${item.level}`),
      fix: translate('fix'),
    };
  }, [t]);
}
