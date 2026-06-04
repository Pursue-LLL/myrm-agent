import type { BrowserRefInfo, ToolApprovalRequest } from '@/store/chat/types';

export interface VisualApprovalBBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface VisualApprovalContext {
  base64: string;
  mimeType: string;
  bbox: VisualApprovalBBox;
  viewportWidth: number;
  viewportHeight: number;
  targetLabel?: string;
  highlightKind: 'ref' | 'coordinate';
}

export interface InspectorViewSnapshot {
  screenshotBase64: string;
  mimeType: string;
  refs: Record<string, BrowserRefInfo>;
  viewportWidth: number;
  viewportHeight: number;
}

const COORDINATE_HIGHLIGHT_SIZE = 48;

export function isVisualApprovalToolName(toolName: string): boolean {
  return toolName.startsWith('desktop_') || toolName.startsWith('browser_');
}

function parseRef(toolInput: Record<string, unknown>): string | null {
  const refStr = toolInput.ref ?? toolInput.element_id ?? toolInput.id;
  return typeof refStr === 'string' && refStr.length > 0 ? refStr : null;
}

function parseCoordinate(toolInput: Record<string, unknown>): [number, number] | null {
  const raw = toolInput.coordinate;
  if (!Array.isArray(raw) || raw.length < 2) {
    return null;
  }
  const x = raw[0];
  const y = raw[1];
  if (typeof x !== 'number' || typeof y !== 'number') {
    return null;
  }
  return [x, y];
}

function bboxFromRef(
  viewData: InspectorViewSnapshot,
  refStr: string,
): VisualApprovalContext | null {
  const targetRef = viewData.refs[refStr];
  if (!targetRef?.bbox) {
    return null;
  }

  return {
    base64: viewData.screenshotBase64,
    mimeType: viewData.mimeType,
    bbox: {
      x: targetRef.bbox.viewport_x ?? targetRef.bbox.x,
      y: targetRef.bbox.viewport_y ?? targetRef.bbox.y,
      width: targetRef.bbox.width,
      height: targetRef.bbox.height,
    },
    viewportWidth: viewData.viewportWidth,
    viewportHeight: viewData.viewportHeight,
    targetLabel: refStr,
    highlightKind: 'ref',
  };
}

function bboxFromCoordinate(
  viewData: InspectorViewSnapshot,
  coordinate: [number, number],
): VisualApprovalContext {
  const [cx, cy] = coordinate;
  const half = COORDINATE_HIGHLIGHT_SIZE / 2;
  const maxX = Math.max(viewData.viewportWidth - COORDINATE_HIGHLIGHT_SIZE, 0);
  const maxY = Math.max(viewData.viewportHeight - COORDINATE_HIGHLIGHT_SIZE, 0);

  return {
    base64: viewData.screenshotBase64,
    mimeType: viewData.mimeType,
    bbox: {
      x: Math.min(Math.max(0, cx - half), maxX),
      y: Math.min(Math.max(0, cy - half), maxY),
      width: COORDINATE_HIGHLIGHT_SIZE,
      height: COORDINATE_HIGHLIGHT_SIZE,
    },
    viewportWidth: viewData.viewportWidth,
    viewportHeight: viewData.viewportHeight,
    targetLabel: `(${cx}, ${cy})`,
    highlightKind: 'coordinate',
  };
}

export function resolveVisualApprovalContext(
  toolName: string,
  toolInput: Record<string, unknown>,
  desktopViewData: InspectorViewSnapshot | null,
  browserViewData: InspectorViewSnapshot | null,
): VisualApprovalContext | null {
  const isDesktop = toolName.startsWith('desktop_');
  const isBrowser = toolName.startsWith('browser_');
  if (!isDesktop && !isBrowser) {
    return null;
  }

  const viewData = isDesktop ? desktopViewData : browserViewData;
  if (!viewData?.screenshotBase64 || viewData.viewportWidth <= 0 || viewData.viewportHeight <= 0) {
    return null;
  }

  const refStr = parseRef(toolInput);
  if (refStr) {
    return bboxFromRef(viewData, refStr);
  }

  if (isDesktop && toolName === 'desktop_vision_tool') {
    const coordinate = parseCoordinate(toolInput);
    if (coordinate) {
      return bboxFromCoordinate(viewData, coordinate);
    }
  }

  return null;
}

export function resolveVisualApprovalContextForRequest(
  request: ToolApprovalRequest,
  desktopViewData: InspectorViewSnapshot | null,
  browserViewData: InspectorViewSnapshot | null,
): VisualApprovalContext | null {
  return resolveVisualApprovalContext(request.toolName, request.toolInput, desktopViewData, browserViewData);
}

export function hasVisualApprovalContext(
  request: ToolApprovalRequest,
  desktopViewData: InspectorViewSnapshot | null,
  browserViewData: InspectorViewSnapshot | null,
): boolean {
  return resolveVisualApprovalContextForRequest(request, desktopViewData, browserViewData) !== null;
}
