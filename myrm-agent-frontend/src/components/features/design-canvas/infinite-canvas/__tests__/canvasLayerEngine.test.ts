import { describe, it, expect } from 'vitest';
import {
  screenToCanvasPoint,
  isLayerIntersectingBox,
  computeLassoInpaintingContext,
  exportLayersToSvg,
  calculateEstimatedSavedTokens,
} from '../canvasLayerEngine';
import { CanvasLayer, CanvasViewport, BoundingBox } from '../infiniteCanvasTypes';

describe('canvasLayerEngine', () => {
  it('projects screen coordinates into canvas coordinate space correctly', () => {
    const viewport: CanvasViewport = { zoom: 2, panX: 50, panY: 100 };
    const containerRect = { left: 200, top: 150 };

    // screenX = 450, localX = 250 -> canvasX = (250 - 50) / 2 = 100
    // screenY = 350, localY = 200 -> canvasY = (200 - 100) / 2 = 50
    const point = screenToCanvasPoint(450, 350, viewport, containerRect);
    expect(point.x).toBe(100);
    expect(point.y).toBe(50);
  });

  it('determines layer intersection with bounding box', () => {
    const layer: CanvasLayer = {
      id: 'layer_title',
      name: '标题',
      type: 'text',
      x: 100,
      y: 100,
      width: 200,
      height: 40,
      opacity: 1,
      isLocked: false,
      zIndex: 1,
      text: '测试标题',
      fontSize: 20,
      fontWeight: 'bold',
      color: '#ffffff',
      fontFamily: 'sans-serif',
    };

    // 框选选区包含该图层 (50, 50) 至 (350, 200)
    const insideBox: BoundingBox = { startX: 50, startY: 50, endX: 350, endY: 200 };
    expect(isLayerIntersectingBox(layer, insideBox)).toBe(true);

    // 选区部分相交 (150, 120) 至 (400, 300)
    const partialBox: BoundingBox = { startX: 150, startY: 120, endX: 400, endY: 300 };
    expect(isLayerIntersectingBox(layer, partialBox)).toBe(true);

    // 选区完全不相交 (500, 500) 至 (600, 600)
    const outsideBox: BoundingBox = { startX: 500, startY: 500, endX: 600, endY: 600 };
    expect(isLayerIntersectingBox(layer, outsideBox)).toBe(false);
  });

  it('computes lasso inpainting context separating target and locked layers', () => {
    const layers: CanvasLayer[] = [
      {
        id: 'layer_1',
        name: '图层1',
        type: 'text',
        x: 50,
        y: 50,
        width: 100,
        height: 50,
        opacity: 1,
        isLocked: false,
        zIndex: 1,
        text: 'L1',
        fontSize: 16,
        fontWeight: 'normal',
        color: '#000',
        fontFamily: 'sans-serif',
      },
      {
        id: 'layer_2',
        name: '图层2',
        type: 'shape',
        shapeType: 'rectangle',
        x: 300,
        y: 300,
        width: 100,
        height: 100,
        opacity: 1,
        isLocked: false,
        zIndex: 2,
        fillColor: '#00ff00',
      },
    ];

    const box: BoundingBox = { startX: 20, startY: 20, endX: 180, endY: 120 };
    const context = computeLassoInpaintingContext(layers, box, '改成粉色背景');

    expect(context.targetLayerIds).toEqual(['layer_1']);
    expect(context.lockedLayerIds).toEqual(['layer_2']);
    expect(context.promptHint).toBe('改成粉色背景');
  });

  it('exports layers to valid lossless SVG markup', () => {
    const layers: CanvasLayer[] = [
      {
        id: 'bg',
        name: '底板',
        type: 'container',
        x: 0,
        y: 0,
        width: 400,
        height: 300,
        opacity: 1,
        isLocked: false,
        zIndex: 1,
        backgroundColor: '#1e293b',
        borderRadius: 8,
        childLayerIds: [],
      },
      {
        id: 'circle_icon',
        name: '圆形图标',
        type: 'shape',
        shapeType: 'circle',
        x: 20,
        y: 20,
        width: 40,
        height: 40,
        opacity: 1,
        isLocked: false,
        zIndex: 2,
        fillColor: '#38bdf8',
      },
      {
        id: 'text_node',
        name: '文字',
        type: 'text',
        x: 80,
        y: 30,
        width: 150,
        height: 30,
        opacity: 1,
        isLocked: false,
        zIndex: 2,
        text: 'SVG 矢量文字',
        fontSize: 18,
        fontWeight: '600',
        color: '#f8fafc',
        fontFamily: 'system-ui',
      },
    ];

    const svg = exportLayersToSvg(layers, 400, 300);
    expect(svg.startsWith('<svg')).toBe(true);
    expect(svg).toContain('<rect x="0" y="0" width="400" height="300"');
    expect(svg).toContain('<circle cx="40" cy="40" r="20"');
    expect(svg).toContain('SVG 矢量文字');
    expect(svg.endsWith('</svg>')).toBe(true);
  });

  it('estimates saved tokens based on inline zero-token edit counts', () => {
    expect(calculateEstimatedSavedTokens(0)).toBe(0);
    expect(calculateEstimatedSavedTokens(1)).toBe(2800);
    expect(calculateEstimatedSavedTokens(5)).toBe(14000);
  });
});
