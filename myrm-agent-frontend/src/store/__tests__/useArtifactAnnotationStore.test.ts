import { describe, expect, it } from 'vitest';
import { useArtifactAnnotationStore } from '../useArtifactAnnotationStore';
import type { ArtifactAnnotation } from '@/lib/artifacts/artifactAnnotations';

function annotation(overrides: Partial<ArtifactAnnotation> = {}): ArtifactAnnotation {
  return {
    id: 'a1',
    artifactId: 'file-1',
    versionId: 'latest',
    anchor: { startLine: 3, endLine: 3, textHash: 'abc', excerpt: 'hello' },
    intent: 'Fix it',
    status: 'open',
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

describe('useArtifactAnnotationStore', () => {
  it('adds and scopes annotations per artifact', () => {
    const store = useArtifactAnnotationStore.getState();
    store.clearArtifact('file-1');
    store.clearArtifact('file-2');
    store.addAnnotation(annotation({ id: 'a1', artifactId: 'file-1' }));
    store.addAnnotation(annotation({ id: 'b1', artifactId: 'file-2' }));
    const state = useArtifactAnnotationStore.getState();
    expect(state.byArtifact['file-1'].map((a) => a.id)).toEqual(['a1']);
    expect(state.byArtifact['file-2'].map((a) => a.id)).toEqual(['b1']);
    store.clearArtifact('file-1');
    store.clearArtifact('file-2');
  });

  it('transitions status and removes entries', () => {    const store = useArtifactAnnotationStore.getState();
    store.clearArtifact('file-1');
    store.addAnnotation(annotation({ id: 'a1' }));
    store.markSubmitted('file-1', ['a1']);
    expect(useArtifactAnnotationStore.getState().byArtifact['file-1'][0].status).toBe('submitted');
    store.markResolved('file-1', ['a1']);
    expect(useArtifactAnnotationStore.getState().byArtifact['file-1'][0].status).toBe('resolved');
    store.removeAnnotation('file-1', 'a1');
    expect(useArtifactAnnotationStore.getState().byArtifact['file-1']).toEqual([]);
  });

  it('persists across reloads and tolerates corrupt payloads', () => {
    const store = useArtifactAnnotationStore.getState();
    store.clearArtifact('file-9');
    store.addAnnotation(annotation({ id: 'p1', artifactId: 'file-9' }));
    const raw = window.localStorage.getItem('myrm.artifact-annotations.v1');
    expect(raw).toContain('p1');
    store.clearArtifact('file-9');
    store.hydrateFromStorage();
    expect(useArtifactAnnotationStore.getState().byArtifact['file-9'].map((a) => a.id)).toEqual(['p1']);
    window.localStorage.setItem('myrm.artifact-annotations.v1', 'not-json{{{');
    store.hydrateFromStorage();
    expect(useArtifactAnnotationStore.getState().byArtifact['file-9']).toBeUndefined();
    window.localStorage.removeItem('myrm.artifact-annotations.v1');
  });
});
