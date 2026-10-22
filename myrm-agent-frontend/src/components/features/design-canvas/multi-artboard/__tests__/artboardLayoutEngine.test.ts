import { describe, it, expect } from 'vitest';
import {
  calculateArtboardGridLayout,
  computeFlowLinkBezierPath,
  applyThemeLockToArtboards,
  extractAllFlowLinksFromArtboards,
} from '../artboardLayoutEngine';
import { Artboard, ThemeLockConfig } from '../multiArtboardTypes';

describe('artboardLayoutEngine', () => {
  const mockArtboards: Artboard[] = [
    {
      id: 'ab-1',
      title: 'Page 1',
      width: 300,
      height: 500,
      x: 0,
      y: 0,
      layers: [
        {
          id: 'l-1',
          name: 'Button 1',
          type: 'button',
          x: 10,
          y: 20,
          width: 100,
          height: 40,
          zIndex: 1,
          opacity: 1,
          targetArtboardId: 'ab-2',
          text: 'Go to Page 2',
        },
      ],
    },
    {
      id: 'ab-2',
      title: 'Page 2',
      width: 300,
      height: 500,
      x: 0,
      y: 0,
      layers: [
        {
          id: 'l-2',
          name: 'Title 2',
          type: 'text',
          x: 10,
          y: 10,
          width: 80,
          height: 20,
          zIndex: 1,
          opacity: 1,
          text: 'Welcome',
        },
      ],
    },
    {
      id: 'ab-3',
      title: 'Page 3',
      width: 300,
      height: 500,
      x: 0,
      y: 0,
      layers: [],
    },
  ];

  it('correctly calculates grid coordinates for multi-artboard layout', () => {
    const layout = calculateArtboardGridLayout(mockArtboards, 2, 50, 60, 10, 20);

    expect(layout.length).toBe(3);
    // 第 1 个: row 0, col 0
    expect(layout[0].x).toBe(10);
    expect(layout[0].y).toBe(20);

    // 第 2 个: row 0, col 1 -> 10 + 1 * (300 + 50) = 360
    expect(layout[1].x).toBe(360);
    expect(layout[1].y).toBe(20);

    // 第 3 个: row 1, col 0 -> 10, 20 + 1 * (500 + 60) = 580
    expect(layout[2].x).toBe(10);
    expect(layout[2].y).toBe(580);
  });

  it('computes bezier path and endpoints between two artboards with layer origin', () => {
    const result = computeFlowLinkBezierPath(
      mockArtboards[0],
      mockArtboards[1],
      mockArtboards[0].layers[0]
    );

    expect(result.pathD).toContain('M ');
    expect(result.pathD).toContain('C ');
    // startX = sourceArtboard.x (0) + layer.x (10) + layer.width (100) = 110
    expect(result.startX).toBe(110);
    // startY = sourceArtboard.y (0) + layer.y (20) + layer.height/2 (20) = 40
    expect(result.startY).toBe(40);
    // endX = targetArtboard.x (0)
    expect(result.endX).toBe(0);
    // endY = targetArtboard.y (0) + targetArtboard.height/2 (250) = 250
    expect(result.endY).toBe(250);
  });

  it('applies theme lock styles when theme lock is active', () => {
    const themeLock: ThemeLockConfig = {
      isLocked: true,
      presetName: 'Test Lock',
      primaryColor: '#ff0000',
      secondaryColor: '#cc0000',
      backgroundColor: '#000000',
      borderRadius: 24,
      fontFamily: 'CustomFont',
    };

    const updated = applyThemeLockToArtboards(mockArtboards, themeLock);
    const buttonLayer = updated[0].layers[0];
    const textLayer = updated[1].layers[0];

    expect(buttonLayer.backgroundColor).toBe('#ff0000');
    expect(buttonLayer.borderRadius).toBe(24);
    expect(buttonLayer.fontFamily).toBe('CustomFont');
    expect(textLayer.fontFamily).toBe('CustomFont');
  });

  it('bypasses style updates when theme lock is inactive', () => {
    const inactiveLock: ThemeLockConfig = {
      isLocked: false,
      presetName: 'Test Lock',
      primaryColor: '#ff0000',
      secondaryColor: '#cc0000',
      backgroundColor: '#000000',
      borderRadius: 24,
      fontFamily: 'CustomFont',
    };

    const unchanged = applyThemeLockToArtboards(mockArtboards, inactiveLock);
    expect(unchanged[0].layers[0].backgroundColor).toBeUndefined();
  });

  it('extracts flow links from artboard layers with targetArtboardId', () => {
    const links = extractAllFlowLinksFromArtboards(mockArtboards);
    expect(links.length).toBe(1);
    expect(links[0].sourceArtboardId).toBe('ab-1');
    expect(links[0].targetArtboardId).toBe('ab-2');
    expect(links[0].label).toBe('Go to Page 2');
  });
});
