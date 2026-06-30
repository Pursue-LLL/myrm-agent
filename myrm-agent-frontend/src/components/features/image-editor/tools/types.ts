export type ToolType = 'select' | 'crop' | 'rect' | 'ellipse' | 'arrow' | 'freehand' | 'text' | 'blur';

export interface Point {
  x: number;
  y: number;
}

export interface DrawOperation {
  tool: ToolType;
  color: string;
  lineWidth: number;
  points: Point[];
  text?: string;
  fontSize?: number;
}

export const PALETTE_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#ffffff'] as const;

export const LINE_WIDTHS = [2, 4] as const;

export const MAX_UNDO_STEPS = 50;

export const MAX_IMAGE_DIMENSION = 2048;
