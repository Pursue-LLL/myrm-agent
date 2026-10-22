/**
 * [INPUT]
 * None (Pure domain types for in-app browser element annotation and commenting)
 *
 * [OUTPUT]
 * Bounding boxes, element DOM metadata, annotation pins, subtree groups, and composer payload contracts.
 *
 * [POS]
 * Domain contract layer for in-app browser element annotation and pinpoint commenting system.
 */

export interface PinBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
  viewportWidth: number;
  viewportHeight: number;
}

export interface ElementDomMetadata {
  cssSelector: string;
  tagName: string;
  classList: string[];
  sanitizedOuterHtml: string;
  innerText: string;
  computedStyles: Record<string, string>;
  subtreeBranch: string;
}

export interface BrowserAnnotationPin {
  id: string;
  index: number;
  box: PinBoundingBox;
  comment: string;
  createdAt: number;
  croppedScreenshotBase64?: string;
  domMetadata?: ElementDomMetadata;
}

export interface AnnotationSubtreeGroup {
  subtreeKey: string;
  subtreeName: string;
  pins: BrowserAnnotationPin[];
}

export interface AnnotationExportPayload {
  chatId: string;
  pageUrl?: string;
  pageTitle?: string;
  totalPins: number;
  groups: AnnotationSubtreeGroup[];
  formattedPrompt: string;
}

export interface BrowserAnnotationState {
  isAnnotating: boolean;
  pins: BrowserAnnotationPin[];
  activePinId: string | null;
  dragStartBox: PinBoundingBox | null;
}

export interface BrowserPreviewAnnotationOverlayProps {
  isAnnotating: boolean;
  onToggleAnnotate: (active: boolean) => void;
  pins: BrowserAnnotationPin[];
  onAddPin: (pin: Omit<BrowserAnnotationPin, 'id' | 'index' | 'createdAt'>) => void;
  onUpdatePinComment: (id: string, comment: string) => void;
  onRemovePin: (id: string) => void;
  onClearAllPins: () => void;
  onExportToComposer: (payload: AnnotationExportPayload) => void;
  viewportWidth: number;
  viewportHeight: number;
  baseScreenshotBase64?: string;
  pageUrl?: string;
  pageTitle?: string;
  className?: string;
}
