/**
 * [INPUT]
 * - prototypeCanvasTypes: PrototypeViewport, PrototypeAnnotation, PrototypeHandoffPayload
 *
 * [OUTPUT]
 * - usePrototypeCanvasStore: Zustand store for prototype canvas state, viewport, annotations, and spec handoff
 *
 * [POS]
 * State management for Intent-to-Interactive Prototype Canvas (Item 46 P0).
 * Strictly under 160 lines. Zero `any`.
 */

import { create } from 'zustand';
import type {
  PrototypeAnnotation,
  PrototypeHandoffPayload,
  PrototypeViewport,
} from './prototypeCanvasTypes';

interface PrototypeCanvasState {
  viewport: PrototypeViewport;
  isAnnotating: boolean;
  annotations: PrototypeAnnotation[];
  activeAnnotationId: string | null;
  handoffPayload: PrototypeHandoffPayload | null;

  setViewport: (viewport: PrototypeViewport) => void;
  setAnnotating: (isAnnotating: boolean) => void;
  setActiveAnnotationId: (id: string | null) => void;
  addAnnotation: (
    item: Omit<PrototypeAnnotation, 'id' | 'createdAt' | 'resolved'>
  ) => string;
  removeAnnotation: (id: string) => void;
  toggleResolveAnnotation: (id: string) => void;
  generateHandoffSpec: (
    prototypeTitle: string,
    intentContent: string
  ) => PrototypeHandoffPayload;
  reset: () => void;
}

export const usePrototypeCanvasStore = create<PrototypeCanvasState>((set, get) => ({
  viewport: 'desktop',
  isAnnotating: false,
  annotations: [],
  activeAnnotationId: null,
  handoffPayload: null,

  setViewport: (viewport: PrototypeViewport) => {
    set({ viewport });
  },

  setAnnotating: (isAnnotating: boolean) => {
    set({ isAnnotating });
  },

  setActiveAnnotationId: (id: string | null) => {
    set({ activeAnnotationId: id });
  },

  addAnnotation: (item) => {
    const id = `anno_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const newAnnotation: PrototypeAnnotation = {
      ...item,
      id,
      createdAt: Date.now(),
      resolved: false,
    };
    set((state) => ({
      annotations: [newAnnotation, ...state.annotations],
      activeAnnotationId: id,
    }));
    return id;
  },

  removeAnnotation: (id: string) => {
    set((state) => ({
      annotations: state.annotations.filter((a) => a.id !== id),
      activeAnnotationId:
        state.activeAnnotationId === id ? null : state.activeAnnotationId,
    }));
  },

  toggleResolveAnnotation: (id: string) => {
    set((state) => ({
      annotations: state.annotations.map((a) => {
        if (a.id === id) {
          return { ...a, resolved: !a.resolved };
        }
        return a;
      }),
    }));
  },

  generateHandoffSpec: (prototypeTitle: string, intentContent: string) => {
    const { annotations } = get();
    const unresolved = annotations.filter((a) => !a.resolved);

    const annotationNotes = unresolved.length > 0
      ? unresolved
          .map((a, idx) => `${idx + 1}. [${a.elementTag} \`${a.elementSelector}\`]: ${a.comment}`)
          .join('\n')
      : '_（无未决修改批注，所有视觉约定均已批准）_';

    const specMarkdown = `# Engineering Handoff Spec: ${prototypeTitle}

> Generated from Live Prototype Canvas at ${new Date().toISOString()}

## 1. User Intent Summary
${intentContent.trim() ? intentContent.slice(0, 1000) : '_由意图文档直接派生的高保真原型_'}

## 2. Visual Contract & Component Annotations
${annotationNotes}

## 3. Implementation Instructions for Code Agent
- 严格遵循原型中的结构、间距与交互反馈；
- 将批注项作为最高优先级改动点落实到业务组件代码中；
- 编写端到端单元测试覆盖上述交互状态机。
`;

    const payload: PrototypeHandoffPayload = {
      prototypeTitle,
      generatedSpecMarkdown: specMarkdown,
      unresolvedAnnotations: unresolved,
      timestamp: Date.now(),
    };

    set({ handoffPayload: payload });
    return payload;
  },

  reset: () => {
    set({
      viewport: 'desktop',
      isAnnotating: false,
      annotations: [],
      activeAnnotationId: null,
      handoffPayload: null,
    });
  },
}));
