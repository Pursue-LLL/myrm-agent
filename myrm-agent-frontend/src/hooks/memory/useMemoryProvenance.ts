/**
 * [INPUT]
 * @/services/memory/verifiableProvenance (POS: Frontend API client service)
 *
 * [OUTPUT]
 * useMemoryProvenance React Hook providing state management for:
 * - Residency verification proofs
 * - Non-repudiable physical destruction receipts
 * - Pre-ingest PII shield inspection
 * - Cryptographic volume token generation
 *
 * [POS]
 * Frontend React Hook for Item 160 VerifiableMemoryProvenanceAndZeroCrossTenantPhysicalIsolationSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  DestructionReceiptResponse,
  PiiShieldResponse,
  ResidencyProofRequest,
  ResidencyProofResponse,
  PhysicalPurgeRequest,
  generateVolumeToken,
  inspectPiiContent,
  provePhysicalResidency,
  purgePhysicalStorage,
} from '@/services/memory/verifiableProvenance';

export interface UseMemoryProvenanceState {
  proof: ResidencyProofResponse | null;
  latestReceipt: DestructionReceiptResponse | null;
  piiInspection: PiiShieldResponse | null;
  loading: boolean;
  error: string | null;
  fetchResidencyProof: (req: ResidencyProofRequest) => Promise<ResidencyProofResponse>;
  executePhysicalPurge: (req: PhysicalPurgeRequest) => Promise<DestructionReceiptResponse>;
  scanPii: (text: string) => Promise<PiiShieldResponse>;
  requestVolumeToken: (
    tenantId: string,
    sandboxId: string,
    volumeId: string
  ) => Promise<string>;
}

export function useMemoryProvenance(): UseMemoryProvenanceState {
  const [proof, setProof] = useState<ResidencyProofResponse | null>(null);
  const [latestReceipt, setLatestReceipt] =
    useState<DestructionReceiptResponse | null>(null);
  const [piiInspection, setPiiInspection] = useState<PiiShieldResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchResidencyProof = useCallback(
    async (req: ResidencyProofRequest): Promise<ResidencyProofResponse> => {
      setLoading(true);
      setError(null);
      try {
        const res = await provePhysicalResidency(req);
        setProof(res);
        return res;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const executePhysicalPurge = useCallback(
    async (req: PhysicalPurgeRequest): Promise<DestructionReceiptResponse> => {
      setLoading(true);
      setError(null);
      try {
        const res = await purgePhysicalStorage(req);
        setLatestReceipt(res);
        return res;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const scanPii = useCallback(
    async (text: string): Promise<PiiShieldResponse> => {
      setLoading(true);
      setError(null);
      try {
        const res = await inspectPiiContent({ text });
        setPiiInspection(res);
        return res;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const requestVolumeToken = useCallback(
    async (
      tenantId: string,
      sandboxId: string,
      volumeId: string
    ): Promise<string> => {
      setLoading(true);
      setError(null);
      try {
        const res = await generateVolumeToken({
          tenant_id: tenantId,
          sandbox_id: sandboxId,
          volume_id: volumeId,
        });
        return res.environment_token;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return {
    proof,
    latestReceipt,
    piiInspection,
    loading,
    error,
    fetchResidencyProof,
    executePhysicalPurge,
    scanPii,
    requestVolumeToken,
  };
}
