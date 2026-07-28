/**
 * 技能发现 Hook
 *
 * 封装搜索、预览和安装外部技能的逻辑。
 */

import { useState, useCallback, useRef } from 'react';
import type { DiscoverySearchResult, DiscoveryPreviewResponse } from '@/services/skill';
import {
  searchDiscoverySkills,
  previewDiscoverySkill,
  installDiscoverySkill,
  uninstallDiscoverySkill,
} from '@/services/skill';

interface UseSkillDiscoveryOptions {
  userId?: string;
}

interface UseSkillDiscoveryReturn {
  results: DiscoverySearchResult[];
  isSearching: boolean;
  isInstalling: string | null;
  isPreviewing: string | null;
  previewResult: DiscoveryPreviewResponse | null;
  searchError: string | null;
  installError: string | null;
  installSuccess: string | null;
  search: (query: string) => Promise<void>;
  preview: (skillId: string, source: string) => Promise<DiscoveryPreviewResponse | null>;
  install: (skillId: string, source: string) => Promise<boolean>;
  uninstall: (skillId: string) => Promise<boolean>;
  isUninstalling: string | null;
  clearResults: () => void;
  clearPreview: () => void;
}

export function useSkillDiscovery(options?: UseSkillDiscoveryOptions): UseSkillDiscoveryReturn {
  const [results, setResults] = useState<DiscoverySearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isInstalling, setIsInstalling] = useState<string | null>(null);
  const [isPreviewing, setIsPreviewing] = useState<string | null>(null);
  const [previewResult, setPreviewResult] = useState<DiscoveryPreviewResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [installSuccess, setInstallSuccess] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const search = useCallback(
    async (query: string) => {
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setIsSearching(true);
      setSearchError(null);
      setInstallError(null);
      setInstallSuccess(null);

      try {
        const response = await searchDiscoverySkills(query, 30, options?.userId);
        setResults(response.results);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setSearchError(error instanceof Error ? error.message : 'Search failed');
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    },
    [options?.userId],
  );

  const preview = useCallback(async (skillId: string, source: string): Promise<DiscoveryPreviewResponse | null> => {
    setIsPreviewing(skillId);
    setPreviewResult(null);

    try {
      const result = await previewDiscoverySkill(skillId, source);
      setPreviewResult(result);
      return result;
    } catch (error) {
      setInstallError(error instanceof Error ? error.message : 'Preview failed');
      return null;
    } finally {
      setIsPreviewing(null);
    }
  }, []);

  const install = useCallback(async (skillId: string, source: string): Promise<boolean> => {
    setIsInstalling(skillId);
    setInstallError(null);
    setInstallSuccess(null);

    try {
      const response = await installDiscoverySkill(skillId, source);
      if (response.success) {
        setInstallSuccess(response.skill_name);
        return true;
      }
      setInstallError(response.error || 'Installation failed');
      return false;
    } catch (error) {
      setInstallError(error instanceof Error ? error.message : 'Installation failed');
      return false;
    } finally {
      setIsInstalling(null);
    }
  }, []);

  const [isUninstalling, setIsUninstalling] = useState<string | null>(null);

  const uninstall = useCallback(async (skillId: string): Promise<boolean> => {
    setIsUninstalling(skillId);
    setInstallError(null);

    try {
      const response = await uninstallDiscoverySkill(skillId);
      if (response.success) {
        setResults((prev) => prev.filter((r) => `local::${r.name}` !== skillId));
        return true;
      }
      setInstallError(response.error || 'Uninstall failed');
      return false;
    } catch (error) {
      setInstallError(error instanceof Error ? error.message : 'Uninstall failed');
      return false;
    } finally {
      setIsUninstalling(null);
    }
  }, []);

  const clearResults = useCallback(() => {
    setResults([]);
    setSearchError(null);
    setInstallError(null);
    setInstallSuccess(null);
  }, []);

  const clearPreview = useCallback(() => {
    setPreviewResult(null);
  }, []);

  return {
    results,
    isSearching,
    isInstalling,
    isPreviewing,
    previewResult,
    searchError,
    installError,
    installSuccess,
    search,
    preview,
    install,
    uninstall,
    isUninstalling,
    clearResults,
    clearPreview,
  };
}
