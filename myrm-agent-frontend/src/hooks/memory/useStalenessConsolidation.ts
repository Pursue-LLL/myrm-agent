/**
 * [INPUT]
 * @/services/memory/stalenessConsolidation::DTOs and API methods
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useStalenessConsolidation: React hook managing memory staleness tracking,
 *   touch recall refresh, repository assertion audit scans, and consolidation proposals.
 *
 * [POS]
 * Hook module for Item 158 AutoMemoryStalenessDecayAndConsolidationAuditSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  ApplyConsolidationRequest,
  ArchiveMemoriesRequest,
  MemoryAuditReportDTO,
  MemoryItemProfileDTO,
  MemoryStatus,
  RegisterMemoryRequest,
  RunAuditRequest,
  TouchRecallRequest,
  applyConsolidation,
  archiveMemories,
  listMemories,
  registerMemory,
  runMemoryAudit,
  touchMemoryRecall,
} from '@/services/memory/stalenessConsolidation';

export interface UseStalenessConsolidationState {
  isLoading: boolean;
  isAuditing: boolean;
  memories: MemoryItemProfileDTO[];
  auditReport: MemoryAuditReportDTO | null;
  error: string | null;
}

export interface UseStalenessConsolidationReturn extends UseStalenessConsolidationState {
  fetchMemories: (status?: MemoryStatus) => Promise<MemoryItemProfileDTO[]>;
  addMemory: (req: RegisterMemoryRequest) => Promise<MemoryItemProfileDTO | null>;
  touchRecall: (req: TouchRecallRequest) => Promise<MemoryItemProfileDTO | null>;
  audit: (req: RunAuditRequest) => Promise<MemoryAuditReportDTO | null>;
  consolidate: (proposalId: string, nowIso?: string) => Promise<MemoryItemProfileDTO | null>;
  archive: (memoryIds: string[]) => Promise<string[]>;
  clearLocalState: () => void;
}

export function useStalenessConsolidation(): UseStalenessConsolidationReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isAuditing, setIsAuditing] = useState<boolean>(false);
  const [memories, setMemories] = useState<MemoryItemProfileDTO[]>([]);
  const [auditReport, setAuditReport] = useState<MemoryAuditReportDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchMemories = useCallback(
    async (status?: MemoryStatus): Promise<MemoryItemProfileDTO[]> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await listMemories(status);
        setMemories(result);
        return result;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to fetch memory records';
        setError(message);
        return [];
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const addMemory = useCallback(
    async (req: RegisterMemoryRequest): Promise<MemoryItemProfileDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const created = await registerMemory(req);
        setMemories((prev) => {
          const index = prev.findIndex((m) => m.memory_id === created.memory_id);
          if (index >= 0) {
            const next = [...prev];
            next[index] = created;
            return next;
          }
          return [created, ...prev];
        });
        return created;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to register memory';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const touchRecall = useCallback(
    async (req: TouchRecallRequest): Promise<MemoryItemProfileDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const updated = await touchMemoryRecall(req);
        setMemories((prev) =>
          prev.map((m) => (m.memory_id === updated.memory_id ? updated : m))
        );
        return updated;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to touch memory recall';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const audit = useCallback(
    async (req: RunAuditRequest): Promise<MemoryAuditReportDTO | null> => {
      setIsAuditing(true);
      setError(null);
      try {
        const report = await runMemoryAudit(req);
        setAuditReport(report);
        return report;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to run memory audit';
        setError(message);
        return null;
      } finally {
        setIsAuditing(false);
      }
    },
    []
  );

  const consolidate = useCallback(
    async (
      proposalId: string,
      nowIso?: string
    ): Promise<MemoryItemProfileDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const payload: ApplyConsolidationRequest = {
          proposal_id: proposalId,
          now_iso: nowIso,
        };
        const consolidatedItem = await applyConsolidation(payload);
        // Refresh memory list
        await fetchMemories();
        return consolidatedItem;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to consolidate proposal ${proposalId}`;
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchMemories]
  );

  const archive = useCallback(
    async (memoryIds: string[]): Promise<string[]> => {
      setIsLoading(true);
      setError(null);
      try {
        const payload: ArchiveMemoriesRequest = { memory_ids: memoryIds };
        const archivedIds = await archiveMemories(payload);
        setMemories((prev) =>
          prev.map((m) =>
            archivedIds.includes(m.memory_id)
              ? { ...m, status: 'archived' }
              : m
          )
        );
        return archivedIds;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to archive memories';
        setError(message);
        return [];
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const clearLocalState = useCallback(() => {
    setIsLoading(false);
    setIsAuditing(false);
    setMemories([]);
    setAuditReport(null);
    setError(null);
  }, []);

  return {
    isLoading,
    isAuditing,
    memories,
    auditReport,
    error,
    fetchMemories,
    addMemory,
    touchRecall,
    audit,
    consolidate,
    archive,
    clearLocalState,
  };
}
