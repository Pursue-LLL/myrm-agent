export type CanvasLayerType = 'text' | 'shape' | 'container';

export interface BaseLayer {
  id: string;
  name: string;
  type: CanvasLayerType;
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
  isLocked: boolean;
  zIndex: number;
}

export interface TextLayer extends BaseLayer {
  type: 'text';
  text: string;
  fontSize: number;
  fontWeight: string;
  color: string;
  fontFamily: string;
}

export interface ShapeLayer extends BaseLayer {
  type: 'shape';
  shapeType: 'rectangle' | 'circle' | 'pill';
  fillColor: string;
  borderColor?: string;
  borderWidth?: number;
  borderRadius?: number;
}

export interface ContainerLayer extends BaseLayer {
  type: 'container';
  backgroundColor: string;
  borderRadius: number;
  childLayerIds: string[];
}

export type CanvasLayer = TextLayer | ShapeLayer | ContainerLayer;

export interface CanvasViewport {
  zoom: number;
  panX: number;
  panY: number;
}

export interface BoundingBox {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
}

export interface InpaintingContext {
  selectedBox: BoundingBox;
  targetLayerIds: string[];
  lockedLayerIds: string[];
  promptHint: string;
}

export type CanvasToolMode = 'select' | 'lasso' | 'pan';

export interface ZeroTokenSavingStats {
  inlineEditCount: number;
  estimatedSavedTokens: number;
}
