/**
 * [INPUT]
 * - None (pure domain model contract)
 *
 * [OUTPUT]
 * - CommandCategory, CommandMatrixEntry, CapabilityHintChip, CommandMatrixState
 *
 * [POS]
 * Client-side domain contracts for Context-Aware Capability Discovery & Command Matrix (Item 38 P0).
 * Strictly under 120 lines. Zero `any`.
 */

export type CommandCategory =
  | 'concurrency_collaboration'
  | 'data_science'
  | 'security_credential'
  | 'memory_knowledge'
  | 'delivery_workflow';

export interface CommandMatrixEntry {
  command: string;
  category: CommandCategory;
  title_zh: string;
  title_en: string;
  description_zh: string;
  description_en: string;
  shortcut?: string | null;
  prompt_template: string;
  tags: string[];
  requires_running_task: boolean;
}

export interface CapabilityHintChip {
  chip_id: string;
  command: string;
  label_zh: string;
  label_en: string;
  reason_zh: string;
  reason_en: string;
  priority: number;
  insert_prompt: string;
}

export interface CommandMatrixState {
  isModalOpen: boolean;
  searchQuery: string;
  selectedCategory: CommandCategory | 'all';
  commands: CommandMatrixEntry[];
  suggestedChips: CapabilityHintChip[];
  masteredCommands: string[];
  selectedIndex: number;
  isLoading: boolean;
  error: string | null;

  // Actions
  openModal: () => void;
  closeModal: () => void;
  toggleModal: () => void;
  setSearchQuery: (query: string) => void;
  setSelectedCategory: (category: CommandCategory | 'all') => void;
  setSelectedIndex: (index: number) => void;
  fetchCatalog: () => Promise<void>;
  fetchSuggestions: (
    sessionId: string,
    status: 'idle' | 'running' | 'paused' | 'interrupted' | 'error',
    runningStepCount: number,
    recentTools: string[],
  ) => Promise<void>;
  markCommandMastered: (command: string) => void;
  dismissChip: (chipId: string, command: string) => void;
  reset: () => void;
}
