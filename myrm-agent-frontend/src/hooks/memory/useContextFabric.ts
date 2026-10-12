/**
 * [INPUT]
 * @/services/memory/contextFabric::DTOs, registerProject, listProjects, extractContextEntities,
 *   linkTextToProjects, sinkProjectInsight
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useContextFabric: React hook managing multi-source context fabric extraction,
 *   project entity linking, and insight sinking.
 *
 * [POS]
 * Hook module for Item 153 CrossSourceWorkContextFabricAndProjectEntityLinkerSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  EntityMatchResultDTO,
  InsightSinkRequestDTO,
  InsightSinkResponseDTO,
  ProjectRegistryEntryDTO,
  WorkContextEntityDTO,
  extractContextEntities,
  linkTextToProjects,
  listProjects,
  registerProject,
  sinkProjectInsight,
} from '@/services/memory/contextFabric';

export interface UseContextFabricState {
  isLoading: boolean;
  isExtracting: boolean;
  isLinking: boolean;
  isSinking: boolean;
  projects: ProjectRegistryEntryDTO[];
  lastExtractedEntities: WorkContextEntityDTO[];
  lastLinkResults: EntityMatchResultDTO[];
  lastSinkResult: InsightSinkResponseDTO | null;
  error: string | null;
}

export interface UseContextFabricReturn extends UseContextFabricState {
  fetchProjects: () => Promise<ProjectRegistryEntryDTO[]>;
  addProject: (entry: ProjectRegistryEntryDTO) => Promise<ProjectRegistryEntryDTO | null>;
  extract: (text: string) => Promise<WorkContextEntityDTO[]>;
  link: (text: string, minConfidence?: number) => Promise<EntityMatchResultDTO[]>;
  sink: (request: InsightSinkRequestDTO) => Promise<InsightSinkResponseDTO | null>;
  reset: () => void;
}

export function useContextFabric(): UseContextFabricReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [isLinking, setIsLinking] = useState<boolean>(false);
  const [isSinking, setIsSinking] = useState<boolean>(false);
  const [projects, setProjects] = useState<ProjectRegistryEntryDTO[]>([]);
  const [lastExtractedEntities, setLastExtractedEntities] = useState<WorkContextEntityDTO[]>([]);
  const [lastLinkResults, setLastLinkResults] = useState<EntityMatchResultDTO[]>([]);
  const [lastSinkResult, setLastSinkResult] = useState<InsightSinkResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async (): Promise<ProjectRegistryEntryDTO[]> => {
    setIsLoading(true);
    setError(null);
    try {
      const list = await listProjects();
      setProjects(list);
      return list;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch registered projects';
      setError(msg);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  const addProject = useCallback(
    async (entry: ProjectRegistryEntryDTO): Promise<ProjectRegistryEntryDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const created = await registerProject(entry);
        setProjects((prev) => {
          const filtered = prev.filter((p) => p.project_id !== created.project_id);
          return [...filtered, created];
        });
        return created;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to register project';
        setError(msg);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const extract = useCallback(async (text: string): Promise<WorkContextEntityDTO[]> => {
    setIsExtracting(true);
    setError(null);
    try {
      const resp = await extractContextEntities({ text });
      setLastExtractedEntities(resp.entities);
      return resp.entities;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to extract context entities';
      setError(msg);
      return [];
    } finally {
      setIsExtracting(false);
    }
  }, []);

  const link = useCallback(
    async (text: string, minConfidence = 0.4): Promise<EntityMatchResultDTO[]> => {
      setIsLinking(true);
      setError(null);
      try {
        const resp = await linkTextToProjects({ text, min_confidence: minConfidence });
        setLastLinkResults(resp.matches);
        return resp.matches;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to link text to projects';
        setError(msg);
        return [];
      } finally {
        setIsLinking(false);
      }
    },
    [],
  );

  const sink = useCallback(
    async (request: InsightSinkRequestDTO): Promise<InsightSinkResponseDTO | null> => {
      setIsSinking(true);
      setError(null);
      try {
        const resp = await sinkProjectInsight(request);
        setLastSinkResult(resp);
        return resp;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to sink project insight';
        setError(msg);
        return null;
      } finally {
        setIsSinking(false);
      }
    },
    [],
  );

  const reset = useCallback((): void => {
    setIsLoading(false);
    setIsExtracting(false);
    setIsLinking(false);
    setIsSinking(false);
    setProjects([]);
    setLastExtractedEntities([]);
    setLastLinkResults([]);
    setLastSinkResult(null);
    setError(null);
  }, []);

  return {
    isLoading,
    isExtracting,
    isLinking,
    isSinking,
    projects,
    lastExtractedEntities,
    lastLinkResults,
    lastSinkResult,
    error,
    fetchProjects,
    addProject,
    extract,
    link,
    sink,
    reset,
  };
}
