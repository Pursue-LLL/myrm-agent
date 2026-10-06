'use client';

import { useEffect, useState } from 'react';

import { getAgentReadiness, type AgentReadinessReport } from '@/services/agent';

export type ImportedAgentReadiness =
  { status: 'loading' } | { status: 'ok'; report: AgentReadinessReport } | { status: 'unavailable' };

const LOADING: ImportedAgentReadiness = { status: 'loading' };

/** Readiness of freshly imported agents, fetched once per id set; a failed check never blocks the result page. */
export function useImportedAgentReadiness(agentIds: string[]): (agentId: string) => ImportedAgentReadiness {
  const [states, setStates] = useState<Record<string, ImportedAgentReadiness>>({});
  // Ids are server-issued tokens without separators, so the joined key is a stable dependency.
  const idsKey = agentIds.join('|');

  useEffect(() => {
    const ids = idsKey ? idsKey.split('|') : [];
    let cancelled = false;
    void Promise.allSettled(ids.map((id) => getAgentReadiness(id))).then((results) => {
      if (cancelled) {
        return;
      }
      setStates(
        Object.fromEntries(
          results.map((outcome, index): [string, ImportedAgentReadiness] => [
            ids[index],
            outcome.status === 'fulfilled' ? { status: 'ok', report: outcome.value } : { status: 'unavailable' },
          ]),
        ),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [idsKey]);

  return (agentId) => states[agentId] ?? LOADING;
}
