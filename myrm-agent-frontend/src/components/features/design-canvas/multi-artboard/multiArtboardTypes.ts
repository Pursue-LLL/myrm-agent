'use client';

export type ArtboardLayerType = 'container' | 'text' | 'button' | 'shape';

export interface ArtboardLayer {
  id: string;
  name: string;
  type: ArtboardLayerType;
  x: number;
  y: number;
  width: number;
  height: number;
  zIndex: number;
  opacity: number;
  // 文本属性
  text?: string;
  fontSize?: number;
  fontWeight?: string;
  fontFamily?: string;
  color?: string;
  // 形状/容器属性
  backgroundColor?: string;
  borderRadius?: number;
  borderColor?: string;
  borderWidth?: number;
  // 交互跳转属性（免后端原型跳转锚点）
  targetArtboardId?: string;
  interactionTooltip?: string;
}

export interface Artboard {
  id: string;
  title: string;
  width: number;
  height: number;
  x: number;
  y: number;
  layers: ArtboardLayer[];
  isLocked?: boolean;
}

export interface ArtboardFlowLink {
  id: string;
  sourceArtboardId: string;
  sourceLayerId: string;
  targetArtboardId: string;
  label?: string;
  transition: 'slide' | 'fade' | 'instant';
}

export interface ThemeLockConfig {
  isLocked: boolean;
  presetName: string;
  primaryColor: string;
  secondaryColor: string;
  backgroundColor: string;
  borderRadius: number;
  fontFamily: string;
}

export type DeviceFrameType = 'iphone' | 'ipad' | 'desktop' | 'frameless';

export interface PrototypePlaybackState {
  isPlaying: boolean;
  currentArtboardId: string | null;
  historyStack: string[];
  deviceFrame: DeviceFrameType;
  showHotspotHints: boolean;
  activeTransition: 'slide' | 'fade' | 'instant';
}

export interface CanvasViewportTransform {
  panX: number;
  panY: number;
  zoom: number;
}
