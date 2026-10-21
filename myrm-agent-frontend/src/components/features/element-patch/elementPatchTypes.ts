/**
 * 工件多元素批注打包暂存与手术刀式局部精准补丁数据模型
 */

export type AnnotationStatus =
  | 'pending'
  | 'staged'
  | 'resolving'
  | 'resolved'
  | 'failed';

export interface ElementBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ElementAnnotationItem {
  id: string;
  artifactId: string;
  selector: string;
  elementTagName: string;
  elementTextSnippet?: string;
  boundingBox: ElementBoundingBox;
  instruction: string;
  status: AnnotationStatus;
  createdAt: number;
  resolvedAt?: number;
}

export interface SurgicalPatchScope {
  targetSelector: string;
  diffInstruction: string;
  prohibitedFullRewrite: boolean;
}

export interface StagedBatchPayload {
  batchId: string;
  artifactId: string;
  annotations: ElementAnnotationItem[];
  promptDirective: string;
  timestamp: number;
}

export interface AnnotationResolveSummary {
  batchId: string;
  totalCount: number;
  resolvedCount: number;
  failedCount: number;
  status: 'in_progress' | 'all_resolved' | 'partially_resolved';
}
