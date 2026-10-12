/**
 * [INPUT]
 * - ./templateTypes::TemplateMarketplaceState
 * - ./templateTypes::AgentTemplateItem
 * - ./templateTypes::CloneOptions
 * - ./templateTypes::TemplateCategory
 *
 * [OUTPUT]
 * - useTemplateMarketplaceStore: Zustand store managing templates, filters, and cloning workflows
 *
 * [POS]
 * State management for Prebuilt Agent App Marketplace.
 * Strictly adheres to 0-any rule and < 400 lines limit.
 */

import { create } from 'zustand';
import type {
  TemplateMarketplaceState,
  AgentTemplateItem,
  TemplateCategory,
  CloneOptions,
} from './templateTypes';

interface TemplateApiResponseItem {
  id: string;
  name: string;
  description?: string;
  avatar_url?: string;
  agent_type: 'individual' | 'team';
  category?: string;
  is_pareto_preset?: boolean;
  cost_reduction_ratio?: number;
  use_cases?: string[];
  members?: Array<{ role: string; name: string; description?: string }>;
  settings_preview?: {
    enabled_builtin_tools: string[];
    skill_ids: string[];
    prebuilt_skill_ids: string[];
    mcp_ids: string[];
    memory_preset: string;
    deploy_mode: string;
    sandbox_bound_note?: string;
    prompt_mode: string;
    personality_style: string;
  };
}

const CATEGORY_WIKI_MAP: Record<string, string[]> = {
  engineering: ['architecture/', 'benchmarks/', 'refactor_plans/', 'runbooks/'],
  office: ['templates/', 'meeting_minutes/', 'policies/', 'archive/'],
  commerce: ['product_catalog/', 'competitor_intel/', 'order_flows/'],
  team: ['shared_knowledge/', 'coordination_rules/', 'member_profiles/'],
  general: ['notes/', 'checklists/', 'resources/'],
};

export const useTemplateMarketplaceStore = create<TemplateMarketplaceState>((set, get) => ({
  templates: [],
  isLoading: false,
  error: null,
  searchQuery: '',
  selectedCategory: 'all',
  activeTemplateForClone: null,
  isCloneWorkbenchOpen: false,
  isCloning: false,
  cloneError: null,

  fetchTemplates: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await fetch('/api/v1/agents/templates', {
        headers: { 'Accept-Language': typeof navigator !== 'undefined' ? navigator.language : 'en' },
      });
      if (!response.ok) {
        throw new Error(`Failed to fetch templates: HTTP ${response.status}`);
      }
      const json = await response.json();
      const rawList: TemplateApiResponseItem[] = json?.data || [];

      const enriched: AgentTemplateItem[] = rawList.map((item) => {
        const cat = item.category || (item.agent_type === 'team' ? 'team' : 'general');
        return {
          id: item.id,
          name: item.name,
          description: item.description,
          avatar_url: item.avatar_url,
          agent_type: item.agent_type,
          category: cat,
          is_pareto_preset: item.is_pareto_preset,
          cost_reduction_ratio: item.cost_reduction_ratio,
          use_cases: item.use_cases || [],
          members: item.members || [],
          settings_preview: item.settings_preview,
          wiki_blueprint: CATEGORY_WIKI_MAP[cat] || CATEGORY_WIKI_MAP.general,
        };
      });

      set({ templates: enriched, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      set({ error: message, isLoading: false });
    }
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query });
  },

  setSelectedCategory: (category: TemplateCategory) => {
    set({ selectedCategory: category });
  },

  openCloneWorkbench: (template: AgentTemplateItem) => {
    set({
      activeTemplateForClone: template,
      isCloneWorkbenchOpen: true,
      cloneError: null,
    });
  },

  closeCloneWorkbench: () => {
    set({
      isCloneWorkbenchOpen: false,
      activeTemplateForClone: null,
      cloneError: null,
      isCloning: false,
    });
  },

  resetCloneState: () => {
    set({ cloneError: null, isCloning: false });
  },

  instantiateTemplate: async (options: CloneOptions) => {
    set({ isCloning: true, cloneError: null });
    try {
      const payload: Record<string, string | boolean> = {};
      if (options.customName?.trim()) {
        payload.custom_name = options.customName.trim();
      }
      if (typeof options.initWikiBlueprint === 'boolean') {
        payload.init_wiki_blueprint = options.initWikiBlueprint;
      }

      const response = await fetch(`/api/v1/agents/instantiate-template/${encodeURIComponent(options.templateId)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept-Language': typeof navigator !== 'undefined' ? navigator.language : 'en',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData?.detail || `Instantiation failed with status ${response.status}`);
      }

      const json = await response.json();
      const created = json?.data || {};

      set({
        isCloning: false,
        isCloneWorkbenchOpen: false,
        activeTemplateForClone: null,
      });

      return {
        id: created.id || options.templateId,
        name: created.name || options.templateId,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Instantiation failed';
      set({ cloneError: message, isCloning: false });
      return null;
    }
  },
}));
