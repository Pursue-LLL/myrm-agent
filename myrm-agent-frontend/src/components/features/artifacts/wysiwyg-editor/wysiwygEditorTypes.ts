export type InlineEditMode = 'preview' | 'editing' | 'saving';

export type FontSizeOption = 'sm' | 'base' | 'lg' | 'xl';

export interface InlineElementStyles {
  color?: string;
  backgroundColor?: string;
  fontSize?: string;
  padding?: string;
  borderRadius?: string;
}

export interface SelectedDomElementInfo {
  selector: string;
  tagName: string;
  textContent: string;
  styles: InlineElementStyles;
  boundingBox?: {
    top: number;
    left: number;
    width: number;
    height: number;
  };
}

export interface MutationDiffSummary {
  id: string;
  timestamp: number;
  selector: string;
  changeType: 'text' | 'style' | 'both';
  originalValue: string;
  newValue: string;
}

export interface ZeroTokenCommitReport {
  version: number;
  savedAt: number;
  latencyMs: number;
  tokenSavedCount: number;
  mutationCount: number;
  contextIngressPrompt: string;
}

export interface WysiwygEditorState {
  mode: InlineEditMode;
  originalHtml: string;
  currentHtml: string;
  selectedElement: SelectedDomElementInfo | null;
  pendingMutations: MutationDiffSummary[];
  lastCommitReport: ZeroTokenCommitReport | null;
}
