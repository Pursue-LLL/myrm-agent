/**
 * [INPUT]
 * - None (Pure domain types)
 *
 * [OUTPUT]
 * - ReferenceDimension: 5 standard dimensions ('file' | 'session' | 'artifact' | 'agent' | 'task')
 * - OmniReferenceItem: Suggestion item in autocomplete menu
 * - ResolvedContextSlice: Bounded context slice extracted for prompts
 * - OmniReferenceState: Zustand store state and action contract
 *
 * [POS]
 * Domain contract for Omni-Context @ reference and cross-session provenance gateway.
 * Strictly adheres to 0-any rule.
 */

export type ReferenceDimension = 'file' | 'session' | 'artifact' | 'agent' | 'task';

export type DimensionFilter = ReferenceDimension | 'all';

export interface OmniReferenceItem {
  dimension: ReferenceDimension;
  target_id: string;
  label: string;
  detail?: string | null;
  icon?: string | null;
  updated_at?: string | null;
  extra?: Record<string, string>;
}

export interface ResolvedContextSlice {
  dimension: ReferenceDimension;
  target_id: string;
  label: string;
  content_slice: string;
  is_truncated: boolean;
  token_estimate: number;
  provenance_uri: string;
}

export interface OmniReferenceState {
  isOpen: boolean;
  searchQuery: string;
  selectedDimension: DimensionFilter;
  selectedIndex: number;
  items: OmniReferenceItem[];
  isLoading: boolean;
  error: string | null;
  activeSlices: Record<string, ResolvedContextSlice>;

  // Actions
  openMenu: (initialQuery?: string) => void;
  closeMenu: () => void;
  setSearchQuery: (query: string) => void;
  setSelectedDimension: (dimension: DimensionFilter) => void;
  setSelectedIndex: (index: number) => void;
  selectNext: () => void;
  selectPrev: () => void;
  fetchSuggestions: (query: string, dimension?: DimensionFilter) => Promise<void>;
  resolveSlice: (item: OmniReferenceItem) => Promise<ResolvedContextSlice | null>;
  clearSlices: () => void;
}
