/**
 * Annotation Editor type definitions.
 * Defines all annotation object shapes, tool types, and editor state contracts.
 */

export type AnnotationTool = 'arrow' | 'rectangle' | 'ellipse' | 'text' | 'freehand' | 'highlight' | 'blur' | 'crop';

export interface Point {
  x: number;
  y: number;
}

interface AnnotationBase {
  id: string;
  tool: AnnotationTool;
  color: string;
  strokeWidth: number;
}

export interface ArrowAnnotation extends AnnotationBase {
  tool: 'arrow';
  start: Point;
  end: Point;
}

export interface RectangleAnnotation extends AnnotationBase {
  tool: 'rectangle';
  start: Point;
  end: Point;
  filled: boolean;
}

export interface EllipseAnnotation extends AnnotationBase {
  tool: 'ellipse';
  center: Point;
  radiusX: number;
  radiusY: number;
  filled: boolean;
}

export interface TextAnnotation extends AnnotationBase {
  tool: 'text';
  position: Point;
  content: string;
  fontSize: number;
}

export interface FreehandAnnotation extends AnnotationBase {
  tool: 'freehand';
  points: Point[];
}

export interface HighlightAnnotation extends AnnotationBase {
  tool: 'highlight';
  start: Point;
  end: Point;
  opacity: number;
}

export interface BlurAnnotation extends AnnotationBase {
  tool: 'blur';
  start: Point;
  end: Point;
  intensity: number;
}

export interface CropAnnotation extends AnnotationBase {
  tool: 'crop';
  start: Point;
  end: Point;
}

export type Annotation =
  | ArrowAnnotation
  | RectangleAnnotation
  | EllipseAnnotation
  | TextAnnotation
  | FreehandAnnotation
  | HighlightAnnotation
  | BlurAnnotation
  | CropAnnotation;

export interface AnnotationEditorState {
  annotations: Annotation[];
  activeTool: AnnotationTool;
  activeColor: string;
  strokeWidth: number;
  fontSize: number;
}

export const DEFAULT_COLORS = [
  '#ef4444', // red
  '#f97316', // orange
  '#eab308', // yellow
  '#22c55e', // green
  '#3b82f6', // blue
  '#8b5cf6', // purple
  '#ffffff', // white
  '#000000', // black
] as const;

export const DEFAULT_STROKE_WIDTH = 4;
export const DEFAULT_FONT_SIZE = 18;
export const MAX_OUTPUT_WIDTH = 2048;
