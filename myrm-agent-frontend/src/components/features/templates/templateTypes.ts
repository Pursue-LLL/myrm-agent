/**
 * [INPUT]
 * - None (Pure domain types)
 *
 * [OUTPUT]
 * - TemplateCategory: Valid industry categorization filters
 * - TemplateMember: Team template member description
 * - AgentTemplateItem: Front-facing template model from API
 * - CloneOptions: Parameters for zero-prompt instantiation
 * - TemplateMarketplaceState: Store state and action contract
 *
 * [POS]
 * Domain contract for prebuilt agent template marketplace and zero-prompt cloning.
 * Strictly adheres to 0-any rule.
 */

export type TemplateCategory = 'all' | 'engineering' | 'office' | 'commerce' | 'team' | 'general';

export interface TemplateMember {
  role: string;
  name: string;
  description?: string;
}

export interface TemplateSettingsPreview {
  enabled_builtin_tools: string[];
  skill_ids: string[];
  prebuilt_skill_ids: string[];
  mcp_ids: string[];
  memory_preset: string;
  deploy_mode: string;
  sandbox_bound_note?: string;
  prompt_mode: string;
  personality_style: string;
}

export interface AgentTemplateItem {
  id: string;
  name: string;
  description?: string;
  avatar_url?: string;
  agent_type: 'individual' | 'team';
  category: string;
  is_pareto_preset?: boolean;
  cost_reduction_ratio?: number;
  use_cases?: string[];
  members?: TemplateMember[];
  settings_preview?: TemplateSettingsPreview;
  wiki_blueprint?: string[];
}

export interface CloneOptions {
  templateId: string;
  customName?: string;
  initWikiBlueprint?: boolean;
}

export interface TemplateMarketplaceState {
  templates: AgentTemplateItem[];
  isLoading: boolean;
  error: string | null;
  searchQuery: string;
  selectedCategory: TemplateCategory;
  activeTemplateForClone: AgentTemplateItem | null;
  isCloneWorkbenchOpen: boolean;
  isCloning: boolean;
  cloneError: string | null;

  // Actions
  fetchTemplates: () => Promise<void>;
  setSearchQuery: (query: string) => void;
  setSelectedCategory: (category: TemplateCategory) => void;
  openCloneWorkbench: (template: AgentTemplateItem) => void;
  closeCloneWorkbench: () => void;
  instantiateTemplate: (options: CloneOptions) => Promise<{ id: string; name: string } | null>;
  resetCloneState: () => void;
}
