/**
 * Skill management Store
 */

import { create } from 'zustand';
import type { Skill, SkillState, SkillStore, SkillFilters } from './types';
import {
  listSkills,
  getUserSkillConfig,
  updateUserSkillConfig,
  getLocalSkillPaths,
  updateLocalSkillPaths,
  scanLocalSkills,
  toggleLocalSkill as apiToggleLocalSkill,
  enableSkill as apiEnableSkill,
  disableSkill as apiDisableSkill,
} from '@/services/skill';

const initialFilters: SkillFilters = {
  search: '',
  category: null,
  tags: [],
  sortBy: 'name',
  sortOrder: 'asc',
};

const initialState: SkillState = {
  isSandboxMode: true,
  marketSkills: [],
  localSkills: [],
  enabledPrebuiltIds: [],
  localSkillPaths: [],
  enabledLocalSkillIds: [],
  defaultLocalPaths: [],
  evolutionStrategy: 'balanced',
  isLoadingMarket: false,
  isLoadingLocal: false,
  isLoadingConfig: false,
  filters: initialFilters,
  error: null,
  lastFetchedConfigUserId: null,
};

function filterSkills(skills: Skill[], filters: SkillFilters): Skill[] {
  return skills.filter((skill) => {
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      const matchesSearch =
        skill.name.toLowerCase().includes(searchLower) ||
        skill.description.toLowerCase().includes(searchLower) ||
        skill.tags.some((tag) => tag.toLowerCase().includes(searchLower));
      if (!matchesSearch) return false;
    }
    if (filters.category && skill.category !== filters.category) {
      return false;
    }
    if (filters.tags.length > 0) {
      const hasMatchingTag = filters.tags.some((filterTag) => skill.tags.includes(filterTag));
      if (!hasMatchingTag) return false;
    }
    return true;
  });
}

const useSkillStore = create<SkillStore>((set, get) => ({
  ...initialState,

  fetchMarketSkills: async (forceRefresh = false) => {
    const { filters, isLoadingMarket, marketSkills } = get();
    if (isLoadingMarket || (!forceRefresh && marketSkills.length > 0)) return;

    set({ isLoadingMarket: true, error: null });
    try {
      const response = await listSkills({
        type: 'prebuilt',
        sortBy: filters.sortBy,
        order: filters.sortOrder,
      });
      set({ marketSkills: response.skills, isLoadingMarket: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch market skills',
        isLoadingMarket: false,
      });
    }
  },

  fetchUserSkillConfig: async (forceRefresh = false) => {
    const { isLoadingConfig, lastFetchedConfigUserId } = get();
    const shouldForceRefresh = forceRefresh;
    const hasLoadedForCurrentUser = lastFetchedConfigUserId !== null;

    if (isLoadingConfig || (!shouldForceRefresh && hasLoadedForCurrentUser)) return;

    set({ isLoadingConfig: true, error: null });
    try {
      const config = await getUserSkillConfig();
      set({
        enabledPrebuiltIds: config.enabled_prebuilt_ids,
        localSkillPaths: config.local_skill_paths || [],
        enabledLocalSkillIds: config.enabled_local_skill_ids || [],
        evolutionStrategy: config.evolution_strategy || 'balanced',
        isLoadingConfig: false,
        lastFetchedConfigUserId: 'sandbox',
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch skill config',
        isLoadingConfig: false,
      });
    }
  },

  fetchLocalSkills: async () => {
    const { isLoadingLocal } = get();
    if (isLoadingLocal) return;

    set({ isLoadingLocal: true, error: null });
    try {
      const response = await scanLocalSkills();
      set({ localSkills: response.skills, isLoadingLocal: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch local skills',
        isLoadingLocal: false,
      });
    }
  },

  fetchLocalSkillPaths: async () => {
    try {
      const response = await getLocalSkillPaths();
      set({
        localSkillPaths: response.paths ?? [],
        defaultLocalPaths: response.default_paths ?? ['~/.claude/skills'],
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch local skill paths',
      });
    }
  },

  enableSkill: async (skillId: string, force: boolean = false) => {
    const { enabledPrebuiltIds, enabledLocalSkillIds, marketSkills, localSkills } = get();
    const isLocal = skillId.startsWith('local::');
    const alreadyEnabled = isLocal ? enabledLocalSkillIds.includes(skillId) : enabledPrebuiltIds.includes(skillId);
    if (alreadyEnabled) return;

    try {
      const result = await apiEnableSkill(skillId, force);

      // Check if blocked by security scan
      if (result.blocked) {
        const allSkills = [...marketSkills, ...localSkills];
        const skill = allSkills.find((s) => s.id === skillId);
        const { SkillBlockedError } = await import('./types');
        throw new SkillBlockedError(skillId, skill?.name || skillId, result.scan_findings);
      }

      // Check if pending permission approval
      if (result.pending_approval) {
        // Find skill to get its name and description
        const allSkills = [...marketSkills, ...localSkills];
        const skill = allSkills.find((s) => s.id === skillId);

        // Throw special error for UI to handle
        const { SkillPermissionRequiredError } = await import('./types');
        throw new SkillPermissionRequiredError(
          skillId,
          skill?.name || skillId,
          result.required_permissions || [],
          skill?.description || '',
        );
      }

      // Success - update enabled list
      if (isLocal) {
        set({ enabledLocalSkillIds: [...enabledLocalSkillIds, skillId] });
      } else {
        set({ enabledPrebuiltIds: [...enabledPrebuiltIds, skillId] });
      }
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to enable skill' });
      throw error;
    }
  },

  disableSkill: async (skillId: string) => {
    const { enabledPrebuiltIds, enabledLocalSkillIds } = get();
    const isLocal = skillId.startsWith('local::');

    try {
      await apiDisableSkill(skillId);
      if (isLocal) {
        set({ enabledLocalSkillIds: enabledLocalSkillIds.filter((id) => id !== skillId) });
      } else {
        set({ enabledPrebuiltIds: enabledPrebuiltIds.filter((id) => id !== skillId) });
      }
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to disable skill' });
      throw error;
    }
  },

  toggleSkill: async (skillId: string) => {
    const { isSkillEnabled, enableSkill, disableSkill } = get();
    if (isSkillEnabled(skillId)) {
      await disableSkill(skillId);
    } else {
      await enableSkill(skillId);
    }
  },

  batchToggleSkills: async (skillIds: string[], enable: boolean) => {
    const { enabledPrebuiltIds, enabledLocalSkillIds } = get();

    const prebuiltIds = skillIds.filter((id) => !id.startsWith('local::'));
    const localIds = skillIds.filter((id) => id.startsWith('local::'));

    let newPrebuiltIds = [...enabledPrebuiltIds];
    if (enable) {
      const toAdd = prebuiltIds.filter((id) => !newPrebuiltIds.includes(id));
      newPrebuiltIds = [...newPrebuiltIds, ...toAdd];
    } else {
      newPrebuiltIds = newPrebuiltIds.filter((id) => !prebuiltIds.includes(id));
    }

    set({ enabledPrebuiltIds: newPrebuiltIds });

    try {
      await updateUserSkillConfig({ enabled_prebuilt_ids: newPrebuiltIds });

      for (const localId of localIds) {
        const isEnabled = enabledLocalSkillIds.includes(localId);
        if (enable && !isEnabled) {
          await apiToggleLocalSkill(localId);
        } else if (!enable && isEnabled) {
          await apiToggleLocalSkill(localId);
        }
      }

      const newLocalIds = enable
        ? [...new Set([...enabledLocalSkillIds, ...localIds])]
        : enabledLocalSkillIds.filter((id) => !localIds.includes(id));
      set({ enabledLocalSkillIds: newLocalIds });
    } catch (error) {
      set({
        enabledPrebuiltIds,
        enabledLocalSkillIds,
        error: error instanceof Error ? error.message : 'Failed to batch toggle skills',
      });
    }
  },

  updateLocalSkillPaths: async (paths: string[]) => {
    const { localSkillPaths } = get();
    set({ localSkillPaths: paths });

    try {
      await updateLocalSkillPaths(paths);
      await get().fetchLocalSkills();
    } catch (error) {
      set({
        localSkillPaths,
        error: error instanceof Error ? error.message : 'Failed to update local skill paths',
      });
      throw error;
    }
  },

  addLocalSkillPath: async (path: string) => {
    const { localSkillPaths } = get();
    if (localSkillPaths.includes(path)) return;
    await get().updateLocalSkillPaths([...localSkillPaths, path]);
  },

  removeLocalSkillPath: async (path: string) => {
    const { localSkillPaths } = get();
    await get().updateLocalSkillPaths(localSkillPaths.filter((p) => p !== path));
  },

  updateEvolutionStrategy: async (strategy: string) => {
    try {
      await updateUserSkillConfig({ evolution_strategy: strategy });
      set({ evolutionStrategy: strategy });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to update evolution strategy' });
    }
  },

  scanLocalSkills: async () => {
    await get().fetchLocalSkills();
  },

  toggleLocalSkill: async (skillId: string) => {
    const { enabledLocalSkillIds } = get();
    const isEnabled = enabledLocalSkillIds.includes(skillId);
    const newEnabledIds = isEnabled
      ? enabledLocalSkillIds.filter((id) => id !== skillId)
      : [...enabledLocalSkillIds, skillId];
    set({ enabledLocalSkillIds: newEnabledIds });

    try {
      await apiToggleLocalSkill(skillId);
    } catch (error) {
      set({
        enabledLocalSkillIds,
        error: error instanceof Error ? error.message : 'Failed to toggle local skill',
      });
      throw error;
    }
  },

  setFilters: (newFilters: Partial<SkillFilters>) => {
    const { filters } = get();
    set({ filters: { ...filters, ...newFilters } });
  },

  clearFilters: () => {
    set({ filters: initialFilters });
  },

  isSkillEnabled: (skillId: string) => {
    const { enabledPrebuiltIds, enabledLocalSkillIds } = get();
    if (skillId.startsWith('local::')) {
      return enabledLocalSkillIds.includes(skillId);
    }
    return enabledPrebuiltIds.includes(skillId);
  },

  getFilteredMarketSkills: () => {
    const { marketSkills, filters } = get();
    return filterSkills(marketSkills, filters);
  },

  getFilteredLocalSkills: () => {
    const { localSkills, filters } = get();
    return filterSkills(localSkills, filters);
  },

  getAllTags: () => {
    const { marketSkills, localSkills } = get();
    const tags = new Set<string>();
    [...marketSkills, ...localSkills].forEach((skill) => {
      skill.tags.forEach((tag) => tags.add(tag));
    });
    return Array.from(tags).sort();
  },

  reset: () => {
    set(initialState);
  },
}));

export default useSkillStore;
