export interface ScratchpadDraftState {
  title: string;
  content: string;
  temporaryTags: string[];
  updatedAt: string;
}

export interface PromoteScratchpadPayload {
  title: string;
  content: string;
  target_project_name?: string | null;
  init_readme?: boolean;
  temporary_tags?: string[];
}

export interface PromotedProjectResponse {
  project_name: string;
  target_directory: string;
  created_files: string[];
  initial_context_prompt: string;
  promoted_at: string;
  provenance_metadata: Record<string, string>;
}

export interface ScratchpadStoreState {
  isOpen: boolean;
  draft: ScratchpadDraftState;
  isPromoting: boolean;
  promotionResult: PromotedProjectResponse | null;
  error: string | null;
  openScratchpad: () => void;
  closeScratchpad: () => void;
  setTitle: (title: string) => void;
  setContent: (content: string) => void;
  setTags: (tags: string[]) => void;
  clearDraft: () => void;
  promoteToProject: (customProjectName?: string) => Promise<PromotedProjectResponse>;
}
