'use client';

import { Artboard, ArtboardFlowLink, ArtboardLayer, ThemeLockConfig } from './multiArtboardTypes';

/**
 * 自动计算多画板网格流式平铺排布坐标
 */
export function calculateArtboardGridLayout(
  artboards: Artboard[],
  columns: number = 3,
  gapX: number = 80,
  gapY: number = 100,
  originX: number = 60,
  originY: number = 60
): Artboard[] {
  const safeColumns = Math.max(1, columns);
  
  return artboards.map((artboard, index) => {
    const col = index % safeColumns;
    const row = Math.floor(index / safeColumns);

    const x = originX + col * (artboard.width + gapX);
    const y = originY + row * (artboard.height + gapY);

    return {
      ...artboard,
      x,
      y,
    };
  });
}

/**
 * 计算两个画板之间的平滑三次贝塞尔交互连线
 */
export function computeFlowLinkBezierPath(
  sourceArtboard: Artboard,
  targetArtboard: Artboard,
  sourceLayer?: ArtboardLayer
): {
  pathD: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  labelX: number;
  labelY: number;
} {
  let startX = sourceArtboard.x + sourceArtboard.width;
  let startY = sourceArtboard.y + sourceArtboard.height / 2;

  if (sourceLayer) {
    startX = sourceArtboard.x + sourceLayer.x + sourceLayer.width;
    startY = sourceArtboard.y + sourceLayer.y + sourceLayer.height / 2;
  }

  const endX = targetArtboard.x;
  const endY = targetArtboard.y + targetArtboard.height / 2;

  const dx = Math.abs(endX - startX) * 0.5;
  const cp1X = startX + Math.max(dx, 40);
  const cp1Y = startY;
  const cp2X = endX - Math.max(dx, 40);
  const cp2Y = endY;

  const pathD = `M ${startX} ${startY} C ${cp1X} ${cp1Y}, ${cp2X} ${cp2Y}, ${endX} ${endY}`;
  const labelX = (startX + endX) / 2;
  const labelY = (startY + endY) / 2 - 12;

  return {
    pathD,
    startX,
    startY,
    endX,
    endY,
    labelX,
    labelY,
  };
}

/**
 * 将视觉风格一致性锁应用到画板及其图层中
 */
export function applyThemeLockToArtboards(
  artboards: Artboard[],
  themeLock: ThemeLockConfig
): Artboard[] {
  if (!themeLock.isLocked) {
    return artboards;
  }

  return artboards.map((artboard) => {
    const updatedLayers = artboard.layers.map((layer) => {
      const updatedLayer = { ...layer };

      if (layer.type === 'button') {
        updatedLayer.backgroundColor = themeLock.primaryColor;
        updatedLayer.borderRadius = themeLock.borderRadius;
        updatedLayer.fontFamily = themeLock.fontFamily;
      } else if (layer.type === 'text') {
        updatedLayer.fontFamily = themeLock.fontFamily;
      } else if (layer.type === 'container') {
        updatedLayer.borderRadius = themeLock.borderRadius;
      }

      return updatedLayer;
    });

    return {
      ...artboard,
      layers: updatedLayers,
    };
  });
}

/**
 * 自动从所有画板图层中解析提取跳转连线
 */
export function extractAllFlowLinksFromArtboards(artboards: Artboard[]): ArtboardFlowLink[] {
  const links: ArtboardFlowLink[] = [];

  for (const artboard of artboards) {
    for (const layer of artboard.layers) {
      if (layer.targetArtboardId) {
        links.push({
          id: `link-${artboard.id}-${layer.id}-${layer.targetArtboardId}`,
          sourceArtboardId: artboard.id,
          sourceLayerId: layer.id,
          targetArtboardId: layer.targetArtboardId,
          label: layer.text || layer.name,
          transition: 'slide',
        });
      }
    }
  }

  return links;
}
