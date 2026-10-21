import { describe, it, expect, beforeEach } from 'vitest';
import { useElementPatchStore } from '../useElementPatchStore';

describe('useElementPatchStore', () => {
  beforeEach(() => {
    useElementPatchStore.getState().reset();
  });

  it('initializes with default clean state', () => {
    const state = useElementPatchStore.getState();
    expect(state.stagedAnnotations).toHaveLength(0);
    expect(state.activeBatch).toBeNull();
    expect(state.isDrawerOpen).toBe(false);
    expect(state.isPickingElement).toBe(false);
    expect(state.selectedAnnotationId).toBeNull();
  });

  it('toggles and manages picking element mode', () => {
    useElementPatchStore.getState().startPicking();
    expect(useElementPatchStore.getState().isPickingElement).toBe(true);

    useElementPatchStore.getState().stopPicking();
    expect(useElementPatchStore.getState().isPickingElement).toBe(false);

    useElementPatchStore.getState().togglePicking();
    expect(useElementPatchStore.getState().isPickingElement).toBe(true);
  });

  it('stages annotations and opens drawer automatically', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'artifact-dash-01',
      selector: '#submit-btn',
      elementTagName: 'button',
      elementTextSnippet: '提交订单',
      boundingBox: { x: 100, y: 200, width: 80, height: 32 },
      instruction: '颜色修改为蓝色，增加 loading 动画',
    });

    const state = useElementPatchStore.getState();
    expect(state.stagedAnnotations).toHaveLength(1);
    expect(state.stagedAnnotations[0].selector).toBe('#submit-btn');
    expect(state.stagedAnnotations[0].status).toBe('pending');
    expect(state.isDrawerOpen).toBe(true);
    expect(state.isPickingElement).toBe(false);
  });

  it('updates annotation instruction and removes single item', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'artifact-dash-01',
      selector: '#header',
      elementTagName: 'header',
      boundingBox: { x: 0, y: 0, width: 500, height: 60 },
      instruction: '初始诉求',
    });

    const id = useElementPatchStore.getState().stagedAnnotations[0].id;
    useElementPatchStore.getState().updateAnnotationInstruction(id, '更新后的诉求');
    expect(useElementPatchStore.getState().stagedAnnotations[0].instruction).toBe('更新后的诉求');

    useElementPatchStore.getState().removeAnnotation(id);
    expect(useElementPatchStore.getState().stagedAnnotations).toHaveLength(0);
    expect(useElementPatchStore.getState().isDrawerOpen).toBe(false);
  });

  it('packages and dispatches staged annotations as a single batch', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'art-preview-55',
      selector: '.title',
      elementTagName: 'h1',
      boundingBox: { x: 20, y: 20, width: 200, height: 40 },
      instruction: '字体加大',
    });

    const payload = useElementPatchStore.getState().packageAndDispatch('art-preview-55');
    expect(payload).not.toBeNull();
    expect(payload?.artifactId).toBe('art-preview-55');
    expect(payload?.annotations).toHaveLength(1);
    expect(payload?.annotations[0].status).toBe('staged');
    expect(useElementPatchStore.getState().activeBatch).toEqual(payload);
    expect(useElementPatchStore.getState().isDrawerOpen).toBe(false);
  });

  it('marks annotation as resolved or failed in batch lifecycle', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'art-preview-55',
      selector: '.title',
      elementTagName: 'h1',
      boundingBox: { x: 20, y: 20, width: 200, height: 40 },
      instruction: '字体加大',
    });

    const payload = useElementPatchStore.getState().packageAndDispatch('art-preview-55');
    expect(payload).not.toBeNull();
    if (payload) {
      const annId = payload.annotations[0].id;

      useElementPatchStore.getState().markAnnotationResolved(annId);
      expect(
        useElementPatchStore.getState().stagedAnnotations.find((a) => a.id === annId)?.status
      ).toBe('resolved');

      useElementPatchStore.getState().markAnnotationFailed(annId);
      expect(
        useElementPatchStore.getState().stagedAnnotations.find((a) => a.id === annId)?.status
      ).toBe('failed');
    }
  });

  it('clears staged queue cleanly', () => {
    useElementPatchStore.getState().stageAnnotation({
      artifactId: 'art-1',
      selector: '.box',
      elementTagName: 'div',
      boundingBox: { x: 0, y: 0, width: 10, height: 10 },
      instruction: 'clear me',
    });

    useElementPatchStore.getState().clearStaged();
    expect(useElementPatchStore.getState().stagedAnnotations).toHaveLength(0);
    expect(useElementPatchStore.getState().isDrawerOpen).toBe(false);
  });
});
