/**
 * 工件画布可视化元素级就地精准编辑与批量注释类型定义
 */

export type CanvasInteractionMode = 'inspect' | 'comment' | 'preview';

export interface ElementStylePatch {
  selector: string;
  tagName: string;
  color?: string;
  backgroundColor?: string;
  fontSize?: string;
  padding?: string;
  textContent?: string;
}

export interface VisualCommentPin {
  id: string;
  index: number;
  x: number;
  y: number;
  selector: string;
  targetTag: string;
  targetPreviewSnippet: string;
  commentText: string;
  createdAt: string;
}

export interface BatchAnnotationPayload {
  artifactId: string;
  totalComments: number;
  comments: VisualCommentPin[];
  appliedStylePatches: ElementStylePatch[];
  compiledPromptInstruction: string;
  dispatchedAt: string;
}

export interface InSituInspectionTarget {
  selector: string;
  tagName: string;
  boundingClientRect: {
    top: number;
    left: number;
    width: number;
    height: number;
  };
  currentStyles: {
    color: string;
    backgroundColor: string;
    fontSize: string;
    padding: string;
  };
  currentText: string;
}
