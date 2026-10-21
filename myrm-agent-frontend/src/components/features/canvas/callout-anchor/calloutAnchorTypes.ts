/**
 * Interactive Callout Anchor & Visual Evidence Binding Types
 * 对话气泡与工件视口空间锚定、交互式引文芯片与构件双向高亮聚焦类型系统
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 状态机与空间几何包围盒强类型定义；
 * 3. 行数严格受控在 200 行以内。
 */

export type CalloutEvidenceType = 'dom' | 'canvas' | '3d' | 'code';

export type CalloutSeverity = 'info' | 'warning' | 'critical';

export type FocusOrigin = 'chip' | 'viewport';

export interface CalloutBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ViewportTransform {
  translateX: number;
  translateY: number;
  scale: number;
}

export interface CalloutAnchor {
  id: string;
  label: string;
  section: string;
  quote: string;
  targetSelector: string;
  evidenceType: CalloutEvidenceType;
  boundingBox: CalloutBoundingBox;
  severity: CalloutSeverity;
  description: string;
  tags: string[];
}

export interface CalloutFocusEventDetail {
  anchorId: string;
  origin: FocusOrigin;
  transform: ViewportTransform;
}
