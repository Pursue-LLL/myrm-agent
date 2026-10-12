/**
 * [INPUT]
 * @/services/memory/experienceFlywheel::DTOs, extractExperiences, ingestExperience,
 *   listExperiences, sniffMinefield
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useExperienceFlywheel: React hook managing project experience extraction,
 *   causal flywheel ingestion, and minefield pre-sniffing alerts.
 *
 * [POS]
 * Hook module for Item 154 ProjectExperienceAndADRFlywheelSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  EngineeringExperienceDTO,
  IngestExperienceResponseDTO,
  MinefieldAlertDTO,
  SniffMinefieldResponseDTO,
  extractExperiences,
  ingestExperience,
  listExperiences,
  sniffMinefield,
} from '@/services/memory/experienceFlywheel';

export interface UseExperienceFlywheelState {
  isLoading: boolean;
  isExtracting: boolean;
  isSniffing: boolean;
  experiences: EngineeringExperienceDTO[];
  extractedExperiences: EngineeringExperienceDTO[];
  minefieldAlerts: MinefieldAlertDTO[];
  advisoryPrompt: string;
  lastIngestResult: IngestExperienceResponseDTO | null;
  error: string | null;
}

export interface UseExperienceFlywheelReturn extends UseExperienceFlywheelState {
  fetchExperiences: (kind?: string) => Promise<EngineeringExperienceDTO[]>;
  extract: (narrative: string, defaultKind?: string) => Promise<EngineeringExperienceDTO[]>;
  ingest: (
    experience: EngineeringExperienceDTO,
    workspaceDir?: string | null,
  ) => Promise<IngestExperienceResponseDTO | null>;
  sniff: (
    planText: string,
    explicitEntities?: string[],
  ) => Promise<SniffMinefieldResponseDTO | null>;
  reset: () => void;
}

export function useExperienceFlywheel(): UseExperienceFlywheelReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [isSniffing, setIsSniffing] = useState<boolean>(false);
  const [experiences, setExperiences] = useState<EngineeringExperienceDTO[]>([]);
  const [extractedExperiences, setExtractedExperiences] = useState<EngineeringExperienceDTO[]>([]);
  const [minefieldAlerts, setMinefieldAlerts] = useState<MinefieldAlertDTO[]>([]);
  const [advisoryPrompt, setAdvisoryPrompt] = useState<string>('');
  const [lastIngestResult, setLastIngestResult] = useState<IngestExperienceResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchExperiences = useCallback(
    async (kind?: string): Promise<EngineeringExperienceDTO[]> => {
      setIsLoading(true);
      setError(null);
      try {
        const list = await listExperiences(kind);
        setExperiences(list);
        return list;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to fetch experiences';
        setError(msg);
        return [];
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const extract = useCallback(
    async (narrative: string, defaultKind = 'bug_experience'): Promise<EngineeringExperienceDTO[]> => {
      setIsExtracting(true);
      setError(null);
      try {
        const resp = await extractExperiences({ narrative, default_kind: defaultKind });
        setExtractedExperiences(resp.experiences);
        return resp.experiences;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to extract experiences';
        setError(msg);
        return [];
      } finally {
        setIsExtracting(false);
      }
    },
    [],
  );

  const ingest = useCallback(
    async (
      experience: EngineeringExperienceDTO,
      workspaceDir: string | null = null,
    ): Promise<IngestExperienceResponseDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await ingestExperience({ experience, workspace_dir: workspaceDir });
        setLastIngestResult(res);
        setExperiences((prev) => {
          const filtered = prev.filter((e) => e.experience_id !== experience.experience_id);
          return [...filtered, experience];
        });
        return res;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to ingest experience';
        setError(msg);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const sniff = useCallback(
    async (
      planText: string,
      explicitEntities: string[] = [],
    ): Promise<SniffMinefieldResponseDTO | null> => {
      setIsSniffing(true);
      setError(null);
      try {
        const resp = await sniffMinefield({
          plan_text: planText,
          explicit_entities: explicitEntities,
        });
        setMinefieldAlerts(resp.alerts);
        setAdvisoryPrompt(resp.advisory_prompt);
        return resp;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to sniff minefield';
        setError(msg);
        return null;
      } finally {
        setIsSniffing(false);
      }
    },
    [],
  );

  const reset = useCallback((): void => {
    setIsLoading(false);
    setIsExtracting(false);
    setIsSniffing(false);
    setExperiences([]);
    setExtractedExperiences([]);
    setMinefieldAlerts([]);
    setAdvisoryPrompt('');
    setLastIngestResult(null);
    setError(null);
  }, []);

  return {
    isLoading,
    isExtracting,
    isSniffing,
    experiences,
    extractedExperiences,
    minefieldAlerts,
    advisoryPrompt,
    lastIngestResult,
    error,
    fetchExperiences,
    extract,
    ingest,
    sniff,
    reset,
  };
}
