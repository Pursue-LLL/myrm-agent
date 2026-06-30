import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderOperation, renderAllOperations } from '../tools/drawingEngine';
import type { DrawOperation } from '../tools/types';

function createMockCtx(): CanvasRenderingContext2D {
  return {
    strokeStyle: '',
    fillStyle: '',
    lineWidth: 0,
    lineCap: 'butt',
    lineJoin: 'miter',
    font: '',
    canvas: { width: 800, height: 600 },
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    strokeRect: vi.fn(),
    ellipse: vi.fn(),
    fillText: vi.fn(),
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    getImageData: vi.fn(() => ({
      data: new Uint8ClampedArray(100 * 4),
      width: 10,
      height: 10,
    })),
    putImageData: vi.fn(),
  } as unknown as CanvasRenderingContext2D;
}

describe('drawingEngine', () => {
  let ctx: CanvasRenderingContext2D;

  beforeEach(() => {
    ctx = createMockCtx();
  });

  describe('renderOperation', () => {
    it('renders rectangle with strokeRect', () => {
      const op: DrawOperation = {
        tool: 'rect',
        color: '#ff0000',
        lineWidth: 2,
        points: [{ x: 10, y: 10 }, { x: 100, y: 100 }],
      };
      renderOperation(ctx, op);
      expect(ctx.strokeRect).toHaveBeenCalledWith(10, 10, 90, 90);
      expect(ctx.strokeStyle).toBe('#ff0000');
    });

    it('renders ellipse with ctx.ellipse', () => {
      const op: DrawOperation = {
        tool: 'ellipse',
        color: '#0000ff',
        lineWidth: 3,
        points: [{ x: 0, y: 0 }, { x: 100, y: 50 }],
      };
      renderOperation(ctx, op);
      expect(ctx.ellipse).toHaveBeenCalledWith(50, 25, 50, 25, 0, 0, Math.PI * 2);
      expect(ctx.stroke).toHaveBeenCalled();
    });

    it('renders arrow with line and arrowhead', () => {
      const op: DrawOperation = {
        tool: 'arrow',
        color: '#00ff00',
        lineWidth: 2,
        points: [{ x: 10, y: 10 }, { x: 100, y: 100 }],
      };
      renderOperation(ctx, op);
      expect(ctx.moveTo).toHaveBeenCalled();
      expect(ctx.lineTo).toHaveBeenCalled();
      expect(ctx.stroke).toHaveBeenCalledTimes(2);
    });

    it('renders freehand path', () => {
      const op: DrawOperation = {
        tool: 'freehand',
        color: '#ff0000',
        lineWidth: 4,
        points: [
          { x: 0, y: 0 },
          { x: 10, y: 10 },
          { x: 20, y: 15 },
        ],
      };
      renderOperation(ctx, op);
      expect(ctx.moveTo).toHaveBeenCalledWith(0, 0);
      expect(ctx.lineTo).toHaveBeenCalledTimes(2);
      expect(ctx.stroke).toHaveBeenCalled();
    });

    it('renders text with fillText', () => {
      const op: DrawOperation = {
        tool: 'text',
        color: '#000000',
        lineWidth: 2,
        points: [{ x: 50, y: 50 }],
        text: 'Hello',
        fontSize: 20,
      };
      renderOperation(ctx, op);
      expect(ctx.fillText).toHaveBeenCalledWith('Hello', 50, 50);
      expect(ctx.font).toBe('bold 20px sans-serif');
    });

    it('renders blur (mosaic) with getImageData/putImageData', () => {
      const op: DrawOperation = {
        tool: 'blur',
        color: '#000',
        lineWidth: 2,
        points: [{ x: 0, y: 0 }, { x: 10, y: 10 }],
      };
      renderOperation(ctx, op);
      expect(ctx.getImageData).toHaveBeenCalledWith(0, 0, 10, 10);
      expect(ctx.putImageData).toHaveBeenCalled();
    });

    it('skips rect with fewer than 2 points', () => {
      const op: DrawOperation = {
        tool: 'rect',
        color: '#ff0000',
        lineWidth: 2,
        points: [{ x: 10, y: 10 }],
      };
      renderOperation(ctx, op);
      expect(ctx.strokeRect).not.toHaveBeenCalled();
    });

    it('skips text without text content', () => {
      const op: DrawOperation = {
        tool: 'text',
        color: '#000',
        lineWidth: 2,
        points: [{ x: 10, y: 10 }],
      };
      renderOperation(ctx, op);
      expect(ctx.fillText).not.toHaveBeenCalled();
    });
  });

  describe('renderAllOperations', () => {
    it('clears canvas, draws base image, then all operations', () => {
      const baseImage = {} as HTMLImageElement;
      const ops: DrawOperation[] = [
        { tool: 'rect', color: '#f00', lineWidth: 2, points: [{ x: 0, y: 0 }, { x: 50, y: 50 }] },
        { tool: 'freehand', color: '#0f0', lineWidth: 3, points: [{ x: 0, y: 0 }, { x: 10, y: 10 }] },
      ];

      renderAllOperations(ctx, baseImage, ops);

      expect(ctx.clearRect).toHaveBeenCalledWith(0, 0, 800, 600);
      expect(ctx.drawImage).toHaveBeenCalledWith(baseImage, 0, 0, 800, 600);
      expect(ctx.strokeRect).toHaveBeenCalled();
      expect(ctx.stroke).toHaveBeenCalled();
    });
  });
});
