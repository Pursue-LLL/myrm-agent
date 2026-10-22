'use client';

export type DesignElementKey = 'what' | 'audience' | 'style' | 'content' | 'format';

export interface DesignElementItem {
  key: DesignElementKey;
  label: string;
  value: string | null;
  isDetected: boolean;
  quickOptions: string[];
}

export interface FiveElementSpec {
  what: DesignElementItem;
  audience: DesignElementItem;
  style: DesignElementItem;
  content: DesignElementItem;
  format: DesignElementItem;
  completenessScore: number; // 0 - 100
}

export interface PreviewLayerItem {
  id: string;
  name: string;
  type: 'container' | 'text' | 'button';
  text?: string;
  bg?: string;
  color?: string;
  borderRadius?: number;
  height?: number;
}

export interface DesignDirectionVariant {
  id: string;
  title: string;
  subtitle: string;
  aestheticCategory: string;
  primaryColor: string;
  accentColor: string;
  backgroundColor: string;
  layoutStructure: 'minimal' | 'bold-visual' | 'structured-card';
  summary: string;
  previewLayers: PreviewLayerItem[];
}
