/**
 * [INPUT]
 * None - Pure TypeScript Contract definitions.
 *
 * [OUTPUT]
 * - DevicePosture, AdaptiveLayoutMode, ScreenOrientation, AdaptiveViewportMetrics
 * - TerminalPtyDimensions, TerminalFontMetrics, UseTerminalPtyOptions
 * - AdaptiveMultiPanelGridProps
 *
 * [POS]
 * Type contracts for Adaptive Responsive Multi-Panel Grid and TUI Terminal PTY Auto-resizer.
 */

import React from 'react';

export type DevicePosture =
  | 'foldable-expanded'
  | 'tablet-landscape'
  | 'mobile-landscape'
  | 'mobile-portrait'
  | 'desktop';

export type AdaptiveLayoutMode =
  | 'dual-panel-golden'
  | 'mobile-landscape-compact'
  | 'single-panel-stacked'
  | 'desktop-tri-panel';

export type ScreenOrientation = 'portrait' | 'landscape';

export interface AdaptiveViewportMetrics {
  width: number;
  height: number;
  aspectRatio: number;
  orientation: ScreenOrientation;
  posture: DevicePosture;
  layoutMode: AdaptiveLayoutMode;
  isFoldable: boolean;
  isMobileLandscape: boolean;
}

export interface TerminalPtyDimensions {
  cols: number;
  rows: number;
  containerWidth: number;
  containerHeight: number;
}

export interface TerminalFontMetrics {
  charWidth: number;
  charHeight: number;
}

export interface UseTerminalPtyOptions {
  fontMetrics?: Partial<TerminalFontMetrics>;
  minCols?: number;
  minRows?: number;
  debounceMs?: number;
  onResizePty?: (dimensions: TerminalPtyDimensions) => void;
}

export interface AdaptiveMultiPanelGridProps {
  leftPanel: React.ReactNode;
  rightPanel: React.ReactNode;
  thirdPanel?: React.ReactNode;
  initialSplitRatio?: number;
  minLeftWidthPx?: number;
  minRightWidthPx?: number;
  overridePosture?: DevicePosture;
  className?: string;
}
