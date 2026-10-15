import {
  CanvasLayer,
  CanvasViewport,
  BoundingBox,
  InpaintingContext,
} from './infiniteCanvasTypes';

export function screenToCanvasPoint(
  screenX: number,
  screenY: number,
  viewport: CanvasViewport,
  containerRect: { left: number; top: number }
): { x: number; y: number } {
  const localX = screenX - containerRect.left;
  const localY = screenY - containerRect.top;

  const canvasX = (localX - viewport.panX) / viewport.zoom;
  const canvasY = (localY - viewport.panY) / viewport.zoom;

  return {
    x: Math.round(canvasX),
    y: Math.round(canvasY),
  };
}

export function isLayerIntersectingBox(layer: CanvasLayer, box: BoundingBox): boolean {
  const minX = Math.min(box.startX, box.endX);
  const maxX = Math.max(box.startX, box.endX);
  const minY = Math.min(box.startY, box.endY);
  const maxY = Math.max(box.startY, box.endY);

  const layerRight = layer.x + layer.width;
  const layerBottom = layer.y + layer.height;

  // 判定矩形重叠
  const noOverlap =
    layer.x > maxX ||
    layerRight < minX ||
    layer.y > maxY ||
    layerBottom < minY;

  return !noOverlap;
}

export function computeLassoInpaintingContext(
  layers: CanvasLayer[],
  box: BoundingBox,
  promptHint: string = ''
): InpaintingContext {
  const targetLayerIds: string[] = [];
  const lockedLayerIds: string[] = [];

  for (let i = 0; i < layers.length; i++) {
    const layer = layers[i];
    if (isLayerIntersectingBox(layer, box)) {
      targetLayerIds.push(layer.id);
    } else {
      lockedLayerIds.push(layer.id);
    }
  }

  return {
    selectedBox: {
      startX: Math.min(box.startX, box.endX),
      startY: Math.min(box.startY, box.endY),
      endX: Math.max(box.startX, box.endX),
      endY: Math.max(box.startY, box.endY),
    },
    targetLayerIds,
    lockedLayerIds,
    promptHint: promptHint.trim(),
  };
}

export function exportLayersToSvg(
  layers: CanvasLayer[],
  width: number = 800,
  height: number = 600
): string {
  const sortedLayers = [...layers].sort((a, b) => a.zIndex - b.zIndex);
  const elements: string[] = [];

  for (let i = 0; i < sortedLayers.length; i++) {
    const layer = sortedLayers[i];
    if (layer.type === 'shape') {
      if (layer.shapeType === 'circle') {
        const cx = layer.x + layer.width / 2;
        const cy = layer.y + layer.height / 2;
        const r = Math.min(layer.width, layer.height) / 2;
        elements.push(
          `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${layer.fillColor}" opacity="${layer.opacity}" />`
        );
      } else {
        const radius = layer.borderRadius || 0;
        elements.push(
          `<rect x="${layer.x}" y="${layer.y}" width="${layer.width}" height="${layer.height}" rx="${radius}" fill="${layer.fillColor}" opacity="${layer.opacity}" />`
        );
      }
    } else if (layer.type === 'container') {
      elements.push(
        `<rect x="${layer.x}" y="${layer.y}" width="${layer.width}" height="${layer.height}" rx="${layer.borderRadius}" fill="${layer.backgroundColor}" opacity="${layer.opacity}" />`
      );
    } else if (layer.type === 'text') {
      elements.push(
        `<text x="${layer.x}" y="${layer.y + layer.fontSize}" font-family="${layer.fontFamily}" font-size="${layer.fontSize}" font-weight="${layer.fontWeight}" fill="${layer.color}" opacity="${layer.opacity}">${layer.text}</text>`
      );
    }
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">\n  ${elements.join('\n  ')}\n</svg>`;
}

export function calculateEstimatedSavedTokens(inlineEditCount: number): number {
  // 平均每次如果重新请求生图抽卡，需消耗约 2800 Token
  return inlineEditCount * 2800;
}
