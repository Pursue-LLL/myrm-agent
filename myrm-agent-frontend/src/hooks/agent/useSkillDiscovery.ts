/**
 * 技能发现 Hook
 *
 * 封装搜索、预览和安装外部技能的逻辑。
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { ApiError } from '@/lib/api';
import type { DiscoverySearchResult, DiscoveryPreviewResponse, DiscoveryInstallResponse } from '@/services/skill';
import {
  searchDiscoverySkills,
  previewDiscoverySkill,
  installDiscoverySkill,
  uninstallDiscoverySkill,
} from '@/services/skill';

interface UseSkillDiscoveryOptions {
  userId?: string;
  agentId?: string;
  mountToAgent?: boolean;
  packageType?: 'all' | 'skill' | 'agent_plugin';
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
  search: (query: string, packageTypeOverride?: 'all' | 'skill' | 'agent_plugin') => Promise<void>;
  preview: (skillId: string, source: string) => Promise<DiscoveryPreviewResponse | null>;
  install: (skillId: string, source: string) => Promise<DiscoveryInstallResponse | null>;
  uninstall: (skillId: string, force?: boolean) => Promise<boolean>;
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
    async (query: string, packageTypeOverride?: 'all' | 'skill' | 'agent_plugin') => {
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setIsSearching(true);
      setSearchError(null);
      setInstallError(null);
      setInstallSuccess(null);

      try {
        const pkgType = packageTypeOverride ?? options?.packageType ?? 'all';
        const response = await searchDiscoverySkills(query, 30, options?.userId, pkgType);
        setResults(response.results);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        setSearchError(error instanceof Error ? error.message : 'Search failed');
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    },
    [options?.userId, options?.packageType],
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

  const install = useCallback(
    async (skillId: string, source: string): Promise<DiscoveryInstallResponse | null> => {
      setIsInstalling(skillId);
      setInstallError(null);
      setInstallSuccess(null);

      try {
        const response = await installDiscoverySkill(skillId, source, {
          agentId: options?.agentId,
          mountToAgent: options?.mountToAgent,
        });
        if (response.success) {
          setInstallSuccess(response.skill_name);
          setResults((prev) =>
            prev.map((r) =>
              r.id === skillId && r.source === source
                ? {
                    ...r,
                    installed_version: response.version || r.version || '1.0.0',
                    installed_skill_id: response.skill_id,
                  }
                : r,
            ),
          );
          return response;
        }
        setInstallError(response.error || 'Installation failed');
        return null;
      } catch (error) {
        setInstallError(error instanceof Error ? error.message : 'Installation failed');
        return null;
      } finally {
        setIsInstalling(null);
      }
    },
    [options?.agentId, options?.mountToAgent],
  );

  const [isUninstalling, setIsUninstalling] = useState<string | null>(null);

  const uninstall = useCallback(async (skillId: string, force: boolean = false): Promise<boolean> => {
    setIsUninstalling(skillId);
    setInstallError(null);

    try {
      const response = await uninstallDiscoverySkill(skillId, force);
      if (response.success) {
        setResults((prev) => prev.filter((r) => (r.installed_skill_id ?? '') !== skillId));
        return true;
      }
      setInstallError(response.error || 'Uninstall failed');
      return false;
    } catch (error) {
      // Dependency guard rejects with 409 DEPENDENTS_EXIST; surface it so the
      // caller can offer a force-uninstall confirmation.
      if (error instanceof ApiError && error.code === 409) {
        throw error;
      }
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

  useEffect(() => {
    const handleSkillPoolUpdated = (event: Event) => {
      const customEvent = event as CustomEvent<{ action?: string; skill_id?: string; uninstalled_skills?: string[] }>;
      const detail = customEvent.detail;
      if (!detail) {
        return;
      }

      if (detail.action === 'uninstall') {
        const uninstalled = new Set([detail.skill_id, ...(detail.uninstalled_skills ?? [])].filter(Boolean));

        setResults((prev) =>
          prev.map((r) => {
            if (
              (r.installed_skill_id && uninstalled.has(r.installed_skill_id)) ||
              uninstalled.has(r.id) ||
              uninstalled.has(r.name)
            ) {
              return {
                ...r,
                installed_version: null,
                installed_skill_id: null,
              };
            }
            return r;
          }),
        );
      } else if (detail.action === 'install') {
        if (detail.skill_id) {
          setResults((prev) =>
            prev.map((r) => {
              if (r.id === detail.skill_id || r.name === detail.skill_id) {
                return {
                  ...r,
                  installed_skill_id: detail.skill_id,
                  installed_version: r.version || '1.0.0',
                };
              }
              return r;
            }),
          );
        }
      }
    };

    window.addEventListener('skill_pool_updated', handleSkillPoolUpdated);
    return () => {
      window.removeEventListener('skill_pool_updated', handleSkillPoolUpdated);
    };
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
