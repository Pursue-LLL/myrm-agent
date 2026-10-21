'use client';

import { create } from 'zustand';
import type { ArtifactAnnotation } from '@/lib/artifacts/artifactAnnotations';

interface ArtifactAnnotationState {
  byArtifact: Record<string, ArtifactAnnotation[]>;
  addAnnotation: (annotation: ArtifactAnnotation) => void;
  removeAnnotation: (artifactId: string, annotationId: string) => void;
  markSubmitted: (artifactId: string, annotationIds: string[]) => void;
  markResolved: (artifactId: string, annotationIds: string[]) => void;
  clearArtifact: (artifactId: string) => void;
  hydrateFromStorage: () => void;
}

function patchStatus(
  list: ArtifactAnnotation[],
  ids: string[],
  status: ArtifactAnnotation['status'],
): ArtifactAnnotation[] {
  const wanted = new Set(ids);
  return list.map((a) => (wanted.has(a.id) ? { ...a, status } : a));
}

const STORAGE_KEY = 'myrm.artifact-annotations.v1';

function readPersisted(): Record<string, ArtifactAnnotation[]> {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) {
      return {};
    }
    const out: Record<string, ArtifactAnnotation[]> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof key === 'string' && Array.isArray(value)) {
        out[key] = (value as ArtifactAnnotation[]).filter(
          (a) => a && typeof a.id === 'string' && a.anchor && typeof a.intent === 'string',
        );
      }
    }
    return out;
  } catch {
    return {};
  }
}

function persist(byArtifact: Record<string, ArtifactAnnotation[]>): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(byArtifact));
  } catch {
    // Quota or privacy mode: annotations stay session-scoped.
  }
}

export const useArtifactAnnotationStore = create<ArtifactAnnotationState>()((set) => {
  const save = (fn: (state: ArtifactAnnotationState) => Partial<ArtifactAnnotationState>) => {
    set((state) => {
      const partial = fn(state);
      persist({ ...state.byArtifact, ...(partial.byArtifact || {}) });
      return partial;
    });
  };
  return {
    byArtifact: {},
    hydrateFromStorage: () => set({ byArtifact: readPersisted() }),
    addAnnotation: (annotation) =>
      save((state) => ({
        byArtifact: {
          ...state.byArtifact,
          [annotation.artifactId]: [...(state.byArtifact[annotation.artifactId] || []), annotation],
        },
      })),
    removeAnnotation: (artifactId, annotationId) =>
      save((state) => ({
        byArtifact: {
          ...state.byArtifact,
          [artifactId]: (state.byArtifact[artifactId] || []).filter((a) => a.id !== annotationId),
        },
      })),
    markSubmitted: (artifactId, annotationIds) =>
      save((state) => ({
        byArtifact: {
          ...state.byArtifact,
          [artifactId]: patchStatus(state.byArtifact[artifactId] || [], annotationIds, 'submitted'),
        },
      })),
    markResolved: (artifactId, annotationIds) =>
      save((state) => ({
        byArtifact: {
          ...state.byArtifact,
          [artifactId]: patchStatus(state.byArtifact[artifactId] || [], annotationIds, 'resolved'),
        },
      })),
    clearArtifact: (artifactId) =>
      save((state) => {
        const next = { ...state.byArtifact };
        delete next[artifactId];
        return { byArtifact: next };
      }),
  };
});
