export interface DesignColorTokens {
  primary: string;
  primaryHover: string;
  surface: string;
  background: string;
  textPrimary: string;
  textMuted: string;
  border: string;
  accent: string;
}

export interface DesignTypographyTokens {
  fontFamilySans: string;
  fontFamilyMono: string;
  headingScale: string;
  bodyLeading: string;
}

export interface DesignGeometryTokens {
  borderRadius: string;
  containerPadding: string;
  shadowLevel: string;
}

export interface DesignSystemTokens {
  colors: DesignColorTokens;
  typography: DesignTypographyTokens;
  geometry: DesignGeometryTokens;
}

export interface DesignSystemSpec {
  specId: string;
  name: string;
  version: string;
  description: string;
  author: string;
  tokens: DesignSystemTokens;
  rawMarkdown: string;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SelectedElementMeta {
  selectorPath: string;
  tagName: string;
  elementId?: string;
  className?: string;
  textContent: string;
  boundingBox: BoundingBox;
  codeSnippet: string;
  generatedPromptSuggestion: string;
}

export interface PublicShareRecord {
  shareId: string;
  artifactId: string;
  publicUrl: string;
  createdAt: string;
  expiresAt: string | null;
  watermarkText: string;
  isRevoked: boolean;
  visitCount: number;
}

export interface VisualArtifactStudioState {
  currentArtifactId: string;
  activeSpec: DesignSystemSpec;
  isInspectMode: boolean;
  hoveredElement: SelectedElementMeta | null;
  selectedElement: SelectedElementMeta | null;
  promptBackfillText: string;
  isShareModalOpen: boolean;
  publicShares: PublicShareRecord[];

  setActiveSpec: (spec: DesignSystemSpec) => void;
  toggleInspectMode: (enabled?: boolean) => void;
  setHoveredElement: (element: SelectedElementMeta | null) => void;
  selectElement: (element: SelectedElementMeta | null) => void;
  clearSelection: () => void;
  setPromptBackfillText: (text: string) => void;
  openShareModal: () => void;
  closeShareModal: () => void;
  generatePublicShare: (artifactId: string, durationHours: number | null, watermarkText?: string) => PublicShareRecord;
  revokePublicShare: (shareId: string) => void;
  resetStudioState: () => void;
}
