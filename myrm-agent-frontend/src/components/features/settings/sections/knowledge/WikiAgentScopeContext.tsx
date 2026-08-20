'use client';

/**
 * [INPUT]
 * React context (POS: Settings Wiki agent scope state container)
 *
 * [OUTPUT]
 * WikiAgentScopeProvider, useWikiAgentScope: URL `?agentId=` scoped context values
 *
 * [POS]
 * Settings Wiki agent vault scope provider. Exposes scopeRevision for child remount hooks.
 */

import { createContext, useContext, useMemo, type ReactNode } from 'react';

export interface WikiAgentScopeValue {
  agentScopeId: string | null;
  scopeRevision: number;
  scopeLabel: string;
}

const WikiAgentScopeContext = createContext<WikiAgentScopeValue | null>(null);

interface WikiAgentScopeProviderProps {
  agentScopeId: string | null;
  scopeRevision: number;
  scopeLabel: string;
  children: ReactNode;
}

export function WikiAgentScopeProvider({
  agentScopeId,
  scopeRevision,
  scopeLabel,
  children,
}: WikiAgentScopeProviderProps) {
  const value = useMemo(() => ({ agentScopeId, scopeRevision, scopeLabel }), [agentScopeId, scopeRevision, scopeLabel]);
  return <WikiAgentScopeContext.Provider value={value}>{children}</WikiAgentScopeContext.Provider>;
}

export function useWikiAgentScope(): WikiAgentScopeValue {
  const context = useContext(WikiAgentScopeContext);
  if (!context) {
    throw new Error('useWikiAgentScope must be used within WikiAgentScopeProvider');
  }
  return context;
}
