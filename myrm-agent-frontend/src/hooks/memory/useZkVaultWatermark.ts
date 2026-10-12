/**
 * [INPUT]
 * @/services/memory/zkVaultWatermark::DTOs and API methods
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useZkVaultWatermark: React hook managing zero-knowledge memory vault operations,
 *   envelope sealing/unsealing, distilled package exports, and invisible provenance watermarking.
 *
 * [POS]
 * Hook module for Item 159 ZeroKnowledgeMemoryVaultAndAntiCloningProvenanceWatermarkingSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  DistilledExportPackageDTO,
  DistilledMemoryItemDTO,
  EncryptedEnvelopeDTO,
  ExportDistilledRequest,
  MemorySensitivityTier,
  ProvenanceWatermarkDTO,
  ResidencyCheckResponse,
  SealMemoryRequest,
  UnlockResidencyRequest,
  UnsealMemoryRequest,
  VerifyResidencyRequest,
  exportDistilledPackage,
  listVaultMemories,
  sealMemory,
  unlockSandboxResidency,
  unsealMemory,
  verifySandboxResidency,
  verifyWatermark,
} from '@/services/memory/zkVaultWatermark';

export interface UseZkVaultWatermarkState {
  isLoading: boolean;
  isVerifying: boolean;
  memories: DistilledMemoryItemDTO[];
  lastExportPackage: DistilledExportPackageDTO | null;
  lastVerifiedWatermark: ProvenanceWatermarkDTO | null;
  residencyStatus: ResidencyCheckResponse | null;
  error: string | null;
}

export interface UseZkVaultWatermarkReturn extends UseZkVaultWatermarkState {
  fetchMemories: (tier?: MemorySensitivityTier) => Promise<DistilledMemoryItemDTO[]>;
  seal: (req: SealMemoryRequest) => Promise<EncryptedEnvelopeDTO | null>;
  unseal: (req: UnsealMemoryRequest) => Promise<DistilledMemoryItemDTO | null>;
  exportPackage: (req: ExportDistilledRequest) => Promise<DistilledExportPackageDTO | null>;
  inspectWatermark: (exportedText: string) => Promise<ProvenanceWatermarkDTO | null>;
  checkResidency: (req: VerifyResidencyRequest) => Promise<ResidencyCheckResponse | null>;
  unlockResidency: (req: UnlockResidencyRequest) => Promise<boolean>;
  clearLocalState: () => void;
}

export function useZkVaultWatermark(): UseZkVaultWatermarkReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [memories, setMemories] = useState<DistilledMemoryItemDTO[]>([]);
  const [lastExportPackage, setLastExportPackage] = useState<DistilledExportPackageDTO | null>(null);
  const [lastVerifiedWatermark, setLastVerifiedWatermark] = useState<ProvenanceWatermarkDTO | null>(null);
  const [residencyStatus, setResidencyStatus] = useState<ResidencyCheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchMemories = useCallback(
    async (tier?: MemorySensitivityTier): Promise<DistilledMemoryItemDTO[]> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await listVaultMemories(tier);
        setMemories(result);
        return result;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to fetch vault memories';
        setError(message);
        return [];
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const seal = useCallback(
    async (req: SealMemoryRequest): Promise<EncryptedEnvelopeDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const envelope = await sealMemory(req);
        // Refresh memory list
        await fetchMemories();
        return envelope;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to seal memory';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchMemories]
  );

  const unseal = useCallback(
    async (req: UnsealMemoryRequest): Promise<DistilledMemoryItemDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const unsealed = await unsealMemory(req);
        setMemories((prev) => {
          const index = prev.findIndex((m) => m.memory_id === unsealed.memory_id);
          if (index >= 0) {
            const next = [...prev];
            next[index] = unsealed;
            return next;
          }
          return [unsealed, ...prev];
        });
        return unsealed;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to unseal memory';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const exportPackage = useCallback(
    async (req: ExportDistilledRequest): Promise<DistilledExportPackageDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const pkg = await exportDistilledPackage(req);
        setLastExportPackage(pkg);
        return pkg;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to export distilled package';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const inspectWatermark = useCallback(
    async (exportedText: string): Promise<ProvenanceWatermarkDTO | null> => {
      setIsVerifying(true);
      setError(null);
      try {
        const wm = await verifyWatermark({ exported_text: exportedText });
        setLastVerifiedWatermark(wm);
        return wm;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'No valid provenance watermark detected';
        setError(message);
        setLastVerifiedWatermark(null);
        return null;
      } finally {
        setIsVerifying(false);
      }
    },
    []
  );

  const checkResidency = useCallback(
    async (req: VerifyResidencyRequest): Promise<ResidencyCheckResponse | null> => {
      setIsVerifying(true);
      setError(null);
      try {
        const status = await verifySandboxResidency(req);
        setResidencyStatus(status);
        return status;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to verify residency';
        setError(message);
        return null;
      } finally {
        setIsVerifying(false);
      }
    },
    []
  );

  const unlockResidency = useCallback(
    async (req: UnlockResidencyRequest): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await unlockSandboxResidency(req);
        if (res.unlocked) {
          setResidencyStatus({ allowed: true, diagnostic: 'Residency unlocked and rebound.' });
        }
        return res.unlocked;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to unlock residency';
        setError(message);
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const clearLocalState = useCallback(() => {
    setIsLoading(false);
    setIsVerifying(false);
    setMemories([]);
    setLastExportPackage(null);
    setLastVerifiedWatermark(null);
    setResidencyStatus(null);
    setError(null);
  }, []);

  return {
    isLoading,
    isVerifying,
    memories,
    lastExportPackage,
    lastVerifiedWatermark,
    residencyStatus,
    error,
    fetchMemories,
    seal,
    unseal,
    exportPackage,
    inspectWatermark,
    checkResidency,
    unlockResidency,
    clearLocalState,
  };
}
