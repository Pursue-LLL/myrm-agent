import { describe, it, expect, beforeEach } from 'vitest';
import { usePrototypeCanvasStore } from '../usePrototypeCanvasStore';

describe('usePrototypeCanvasStore', () => {
  beforeEach(() => {
    usePrototypeCanvasStore.getState().reset();
  });

  it('initializes with default desktop viewport and empty annotations', () => {
    const state = usePrototypeCanvasStore.getState();
    expect(state.viewport).toBe('desktop');
    expect(state.isAnnotating).toBe(false);
    expect(state.annotations).toEqual([]);
    expect(state.activeAnnotationId).toBeNull();
    expect(state.handoffPayload).toBeNull();
  });

  it('updates viewport properly across desktop, tablet, and mobile', () => {
    const store = usePrototypeCanvasStore.getState();
    store.setViewport('tablet');
    expect(usePrototypeCanvasStore.getState().viewport).toBe('tablet');

    store.setViewport('mobile');
    expect(usePrototypeCanvasStore.getState().viewport).toBe('mobile');

    store.setViewport('desktop');
    expect(usePrototypeCanvasStore.getState().viewport).toBe('desktop');
  });

  it('toggles annotating state correctly', () => {
    const store = usePrototypeCanvasStore.getState();
    store.setAnnotating(true);
    expect(usePrototypeCanvasStore.getState().isAnnotating).toBe(true);

    store.setAnnotating(false);
    expect(usePrototypeCanvasStore.getState().isAnnotating).toBe(false);
  });

  it('adds, resolves, and removes annotations', () => {
    const store = usePrototypeCanvasStore.getState();

    const id1 = store.addAnnotation({
      elementTag: 'button',
      elementSelector: '.btn-primary',
      comment: '改为渐变紫并在右侧增加图标',
      position: { x: 120, y: 80 },
    });

    const stateAfterAdd = usePrototypeCanvasStore.getState();
    expect(stateAfterAdd.annotations.length).toBe(1);
    expect(stateAfterAdd.annotations[0].id).toBe(id1);
    expect(stateAfterAdd.annotations[0].resolved).toBe(false);
    expect(stateAfterAdd.activeAnnotationId).toBe(id1);

    // Toggle resolve
    store.toggleResolveAnnotation(id1);
    expect(usePrototypeCanvasStore.getState().annotations[0].resolved).toBe(true);

    // Toggle back
    store.toggleResolveAnnotation(id1);
    expect(usePrototypeCanvasStore.getState().annotations[0].resolved).toBe(false);

    // Remove
    store.removeAnnotation(id1);
    const stateAfterRemove = usePrototypeCanvasStore.getState();
    expect(stateAfterRemove.annotations.length).toBe(0);
    expect(stateAfterRemove.activeAnnotationId).toBeNull();
  });

  it('generates engineering handoff spec with markdown and unresolved notes', () => {
    const store = usePrototypeCanvasStore.getState();

    store.addAnnotation({
      elementTag: 'input',
      elementSelector: '#search-box',
      comment: '增加回车即时搜索与防抖过滤',
    });

    const payload = store.generateHandoffSpec(
      'Search Hub Prototype',
      '# Intent: 提供极速全文搜索原型'
    );

    expect(payload.prototypeTitle).toBe('Search Hub Prototype');
    expect(payload.unresolvedAnnotations.length).toBe(1);
    expect(payload.generatedSpecMarkdown).toContain('# Engineering Handoff Spec: Search Hub Prototype');
    expect(payload.generatedSpecMarkdown).toContain('Search Hub Prototype');
    expect(payload.generatedSpecMarkdown).toContain('#search-box');
    expect(payload.generatedSpecMarkdown).toContain('增加回车即时搜索与防抖过滤');
    expect(usePrototypeCanvasStore.getState().handoffPayload).toEqual(payload);
  });

  it('resets state completely to initial baseline', () => {
    const store = usePrototypeCanvasStore.getState();
    store.setViewport('mobile');
    store.setAnnotating(true);
    store.addAnnotation({
      elementTag: 'header',
      elementSelector: '.top-nav',
      comment: '固定置顶',
    });

    store.reset();
    const resetState = usePrototypeCanvasStore.getState();
    expect(resetState.viewport).toBe('desktop');
    expect(resetState.isAnnotating).toBe(false);
    expect(resetState.annotations).toEqual([]);
    expect(resetState.activeAnnotationId).toBeNull();
    expect(resetState.handoffPayload).toBeNull();
  });
});
