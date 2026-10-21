import { describe, it, expect, beforeEach } from 'vitest';
import { useInsituAnnotationStore } from '../useInsituAnnotationStore';

describe('useInsituAnnotationStore 状态管理单测', () => {
  beforeEach(() => {
    useInsituAnnotationStore.setState({
      artifactId: 'test-art-1',
      mode: 'comment',
      comments: [],
      stylePatches: [],
      activeCommentId: null,
      inspectionTarget: null,
      isRailOpen: true,
    });
  });

  it('初始状态具备默认模式与空的批注及补丁列表', () => {
    const state = useInsituAnnotationStore.getState();
    expect(state.artifactId).toBe('test-art-1');
    expect(state.mode).toBe('comment');
    expect(state.comments.length).toBe(0);
    expect(state.stylePatches.length).toBe(0);
  });

  it('addCommentPin 能添加批注钉并自增序号 index', () => {
    const pin1 = useInsituAnnotationStore.getState().addCommentPin({
      x: 100,
      y: 120,
      selector: '#btn-1',
      targetTag: 'button',
      targetPreviewSnippet: '<button>OK</button>',
      commentText: '改文字',
    });

    const pin2 = useInsituAnnotationStore.getState().addCommentPin({
      x: 200,
      y: 220,
      selector: '.title',
      targetTag: 'h1',
      targetPreviewSnippet: '<h1>Title</h1>',
      commentText: '改颜色',
    });

    expect(pin1.index).toBe(1);
    expect(pin2.index).toBe(2);
    expect(useInsituAnnotationStore.getState().comments.length).toBe(2);
    expect(useInsituAnnotationStore.getState().activeCommentId).toBe(pin2.id);
  });

  it('removeCommentPin 删除批注后能重新对剩余批注从 1 开始编号', () => {
    const pin1 = useInsituAnnotationStore.getState().addCommentPin({
      x: 100,
      y: 100,
      selector: 'div',
      targetTag: 'div',
      targetPreviewSnippet: 'A',
      commentText: 'A',
    });
    const pin2 = useInsituAnnotationStore.getState().addCommentPin({
      x: 200,
      y: 200,
      selector: 'p',
      targetTag: 'p',
      targetPreviewSnippet: 'B',
      commentText: 'B',
    });

    useInsituAnnotationStore.getState().removeCommentPin(pin1.id);

    const remaining = useInsituAnnotationStore.getState().comments;
    expect(remaining.length).toBe(1);
    expect(remaining[0].id).toBe(pin2.id);
    expect(remaining[0].index).toBe(1); // 原本是 2，重新整理为 1
  });

  it('upsertStylePatch 与 removeStylePatch 正确管理样式补丁', () => {
    useInsituAnnotationStore.getState().upsertStylePatch({
      selector: '#btn',
      tagName: 'button',
      color: '#fff',
    });
    expect(useInsituAnnotationStore.getState().stylePatches.length).toBe(1);

    // 覆盖更新同一个 selector
    useInsituAnnotationStore.getState().upsertStylePatch({
      selector: '#btn',
      tagName: 'button',
      color: '#000',
      backgroundColor: '#ccc',
    });
    expect(useInsituAnnotationStore.getState().stylePatches.length).toBe(1);
    expect(useInsituAnnotationStore.getState().stylePatches[0].color).toBe('#000');

    // 删除补丁
    useInsituAnnotationStore.getState().removeStylePatch('#btn');
    expect(useInsituAnnotationStore.getState().stylePatches.length).toBe(0);
  });

  it('clearAll 彻底清空所有临时批注与补丁', () => {
    useInsituAnnotationStore.getState().addCommentPin({
      x: 50,
      y: 50,
      selector: 'span',
      targetTag: 'span',
      targetPreviewSnippet: 'test',
      commentText: 'test',
    });
    useInsituAnnotationStore.getState().clearAll();

    expect(useInsituAnnotationStore.getState().comments.length).toBe(0);
    expect(useInsituAnnotationStore.getState().stylePatches.length).toBe(0);
    expect(useInsituAnnotationStore.getState().activeCommentId).toBeNull();
  });
});
