/**
 * [INPUT]
 * @/services/memory/domainIsolation::DTOs and API methods
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useDomainIsolation: React hook managing connector-domain bindings,
 *   domain-scoped permissions (write, recall, egress), and active domain context.
 *
 * [POS]
 * Hook module for Item 156 ConnectionAndAccountDomainIsolation.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  ConnectorDomainBindingDTO,
  DataDomain,
  DomainGrantConfigDTO,
  EgressDecisionDTO,
  SetConnectorDomainRequest,
  UpdateDomainGrantRequest,
  ValidateRecallResponse,
  ValidateWriteResponse,
  deleteConnectorBinding,
  evaluateChannelEgress,
  listConnectorBindings,
  listDomainGrants,
  setConnectorBinding,
  updateDomainGrant,
  validateDomainRecall,
  validateDomainWrite,
} from '@/services/memory/domainIsolation';

export interface UseDomainIsolationState {
  isLoading: boolean;
  isEvaluating: boolean;
  bindings: ConnectorDomainBindingDTO[];
  grants: DomainGrantConfigDTO[];
  activeDomain: DataDomain;
  lastEgressDecision: EgressDecisionDTO | null;
  error: string | null;
}

export interface UseDomainIsolationReturn extends UseDomainIsolationState {
  setActiveDomain: (domain: DataDomain) => void;
  fetchBindings: (domain?: DataDomain) => Promise<ConnectorDomainBindingDTO[]>;
  bindConnector: (
    req: SetConnectorDomainRequest
  ) => Promise<ConnectorDomainBindingDTO | null>;
  unbindConnector: (connectorId: string) => Promise<boolean>;
  fetchGrants: () => Promise<DomainGrantConfigDTO[]>;
  modifyGrant: (
    domain: DataDomain,
    req: UpdateDomainGrantRequest
  ) => Promise<DomainGrantConfigDTO | null>;
  checkRecall: (
    targetDomain: DataDomain,
    allowCrossDomain?: boolean
  ) => Promise<ValidateRecallResponse | null>;
  checkWrite: (domain: DataDomain) => Promise<ValidateWriteResponse | null>;
  checkEgress: (
    contentDomain: DataDomain,
    targetChannel: string,
    userConfirmed?: boolean
  ) => Promise<EgressDecisionDTO | null>;
  reset: () => void;
}

export function useDomainIsolation(): UseDomainIsolationReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [bindings, setBindings] = useState<ConnectorDomainBindingDTO[]>([]);
  const [grants, setGrants] = useState<DomainGrantConfigDTO[]>([]);
  const [activeDomain, setActiveDomain] = useState<DataDomain>('work');
  const [lastEgressDecision, setLastEgressDecision] = useState<EgressDecisionDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchBindings = useCallback(
    async (domain?: DataDomain): Promise<ConnectorDomainBindingDTO[]> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await listConnectorBindings(domain);
        setBindings(result);
        return result;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to fetch connector bindings';
        setError(message);
        return [];
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const bindConnector = useCallback(
    async (req: SetConnectorDomainRequest): Promise<ConnectorDomainBindingDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const saved = await setConnectorBinding(req);
        setBindings((prev) => {
          const index = prev.findIndex((b) => b.connector_id === req.connector_id);
          if (index >= 0) {
            const next = [...prev];
            next[index] = saved;
            return next;
          }
          return [saved, ...prev];
        });
        return saved;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to bind connector';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const unbindConnector = useCallback(
    async (connectorId: string): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await deleteConnectorBinding(connectorId);
        setBindings((prev) => prev.filter((b) => b.connector_id !== connectorId));
        return true;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to unbind connector ${connectorId}`;
        setError(message);
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const fetchGrants = useCallback(async (): Promise<DomainGrantConfigDTO[]> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await listDomainGrants();
      setGrants(result);
      return result;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch domain grants';
      setError(message);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  const modifyGrant = useCallback(
    async (
      domain: DataDomain,
      req: UpdateDomainGrantRequest
    ): Promise<DomainGrantConfigDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const updated = await updateDomainGrant(domain, req);
        setGrants((prev) => prev.map((g) => (g.domain === domain ? updated : g)));
        return updated;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to update grant for ${domain}`;
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const checkRecall = useCallback(
    async (
      targetDomain: DataDomain,
      allowCrossDomain = false
    ): Promise<ValidateRecallResponse | null> => {
      setIsEvaluating(true);
      setError(null);
      try {
        return await validateDomainRecall({
          target_domain: targetDomain,
          active_domain: activeDomain,
          allow_cross_domain: allowCrossDomain,
        });
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to validate recall';
        setError(message);
        return null;
      } finally {
        setIsEvaluating(false);
      }
    },
    [activeDomain]
  );

  const checkWrite = useCallback(
    async (domain: DataDomain): Promise<ValidateWriteResponse | null> => {
      setIsEvaluating(true);
      setError(null);
      try {
        return await validateDomainWrite({ domain });
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to validate write for ${domain}`;
        setError(message);
        return null;
      } finally {
        setIsEvaluating(false);
      }
    },
    []
  );

  const checkEgress = useCallback(
    async (
      contentDomain: DataDomain,
      targetChannel: string,
      userConfirmed = false
    ): Promise<EgressDecisionDTO | null> => {
      setIsEvaluating(true);
      setError(null);
      try {
        const decision = await evaluateChannelEgress({
          content_domain: contentDomain,
          target_channel: targetChannel,
          user_confirmed: userConfirmed,
        });
        setLastEgressDecision(decision);
        return decision;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to evaluate channel egress';
        setError(message);
        return null;
      } finally {
        setIsEvaluating(false);
      }
    },
    []
  );

  const reset = useCallback(() => {
    setIsLoading(false);
    setIsEvaluating(false);
    setBindings([]);
    setGrants([]);
    setActiveDomain('work');
    setLastEgressDecision(null);
    setError(null);
  }, []);

  return {
    isLoading,
    isEvaluating,
    bindings,
    grants,
    activeDomain,
    lastEgressDecision,
    error,
    setActiveDomain,
    fetchBindings,
    bindConnector,
    unbindConnector,
    fetchGrants,
    modifyGrant,
    checkRecall,
    checkWrite,
    checkEgress,
    reset,
  };
}
