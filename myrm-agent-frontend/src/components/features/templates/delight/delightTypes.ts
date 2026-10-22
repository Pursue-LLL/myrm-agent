/**
 * [INPUT]
 * - None (domain contract types)
 *
 * [OUTPUT]
 * - DelightCategory, DelightTemplateItem, SingleFileSandboxContractItem, SandboxValidationResultItem, DelightShowcaseState
 *
 * [POS]
 * Client-side domain contracts for Zero-Code Hobbyist Delight & Single-File Sandbox (Item 40 P0).
 * Strictly under 120 lines. Zero `any`.
 */

export type DelightCategory =
  | "all"
  | "celebration"
  | "interactive_fun"
  | "romance_memory"
  | "utility_tools"
  | "generative_art";

export interface DelightTemplateItem {
  template_id: string;
  title: string;
  category: string;
  description: string;
  prompt_seed: string;
  html_source?: string;
  tags: string[];
  icon_name: string;
  is_featured: boolean;
  created_at_ms: number;
}

export interface SingleFileSandboxContractItem {
  contract_id: string;
  session_id: string;
  title: string;
  has_canvas: boolean;
  has_audio: boolean;
  has_tailwind: boolean;
  is_self_contained: boolean;
  compiled_html: string;
  finalized_at_ms: number;
}

export interface SandboxValidationResultItem {
  is_valid: boolean;
  issues: string[];
  has_canvas: boolean;
  has_audio: boolean;
  has_tailwind: boolean;
  compiled_html: string;
}

export interface DelightShowcaseState {
  templates: DelightTemplateItem[];
  selectedCategory: DelightCategory;
  searchQuery: string;
  activeTemplate: DelightTemplateItem | null;
  activeSandboxHtml: string | null;
  activeSandboxTitle: string | null;
  isGalleryOpen: boolean;
  isShowcaseOpen: boolean;
  isQrCodeOpen: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  setGalleryOpen: (open: boolean) => void;
  setShowcaseOpen: (open: boolean) => void;
  setQrCodeOpen: (open: boolean) => void;
  setSelectedCategory: (category: DelightCategory) => void;
  setSearchQuery: (query: string) => void;
  setActiveTemplate: (template: DelightTemplateItem | null) => void;
  openShowcaseWithHtml: (title: string, html: string) => void;
  closeShowcase: () => void;
  fetchTemplates: () => Promise<void>;
  fetchTemplateDetail: (templateId: string) => Promise<DelightTemplateItem | null>;
  validateAndCompileSandbox: (
    chatId: string,
    title: string,
    htmlSource: string
  ) => Promise<SandboxValidationResultItem | null>;
  reset: () => void;
}
