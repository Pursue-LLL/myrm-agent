export type ElementEditorMode = 'preview' | 'inspect' | 'in_place_editing';

export interface BoundingRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export interface InspectorElementInfo {
  id: string;
  tag: string;
  selector: string;
  xpath: string;
  rect: BoundingRect;
  innerText: string;
  classes: string;
  sourceFilePath?: string;
  sourceLine?: number;
}

export type EditPromptCategory = 'style' | 'content' | 'layout' | 'custom';

export interface InPlacePromptPayload {
  element: InspectorElementInfo;
  instruction: string;
  category: EditPromptCategory;
}

export interface SnapshotDiffStats {
  addedLines: number;
  removedLines: number;
  changedTarget: string;
}

export interface ArtifactVersionSnapshot {
  id: string;
  versionNumber: number;
  timestamp: string;
  description: string;
  contentHtml: string;
  diffStats: SnapshotDiffStats;
}
