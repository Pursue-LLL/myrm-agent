import { describe, it, expect, beforeEach } from 'vitest';
import { useElementEditorStore } from '../useElementEditorStore';
import { InspectorElementInfo } from '../elementEditorTypes';

describe('useElementEditorStore', () => {
  const dummyElement: InspectorElementInfo = {
    id: 'btn-test',
    tag: 'button',
    selector: 'button#btn-test',
    xpath: '//button',
    rect: { top: 10, left: 20, width: 100, height: 40 },
    innerText: '立即购买',
    classes: 'btn btn-primary',
  };

  beforeEach(() => {
    useElementEditorStore.getState().resetStore();
  });

  it('初始状态应处于 inspect 模式并包含基础快照', () => {
    const state = useElementEditorStore.getState();
    expect(state.mode).toBe('inspect');
    expect(state.snapshots.length).toBe(1);
    expect(state.currentSnapshotIndex).toBe(0);
    expect(state.hoveredElement).toBeNull();
    expect(state.selectedElement).toBeNull();
  });

  it('setSelectedElement 应切换模式至 in_place_editing', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    expect(useElementEditorStore.getState().mode).toBe('in_place_editing');
    expect(useElementEditorStore.getState().selectedElement).toEqual(dummyElement);
  });

  it('applyMicroPatch 应压入新快照并自动切回 inspect 模式', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    useElementEditorStore.getState().applyMicroPatch('按钮换成紫灰渐变', 'style');

    const state = useElementEditorStore.getState();
    expect(state.snapshots.length).toBe(2);
    expect(state.currentSnapshotIndex).toBe(1);
    expect(state.snapshots[1].description).toContain('按钮换成紫灰渐变');
    expect(state.mode).toBe('inspect');
    expect(state.selectedElement).toBeNull();
    expect(state.lastSynthesizedPrompt).toContain('[外科手术式微补丁请求]');
  });

  it('undo 与 redo 应在历史快照间原子切换', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    useElementEditorStore.getState().applyMicroPatch('版本2修改', 'style');

    expect(useElementEditorStore.getState().currentSnapshotIndex).toBe(1);

    // 悔棋撤销
    const undoRes = useElementEditorStore.getState().undo();
    expect(undoRes).toBe(true);
    expect(useElementEditorStore.getState().currentSnapshotIndex).toBe(0);

    // 再次撤销应返回 false（已是最初版）
    expect(useElementEditorStore.getState().undo()).toBe(false);

    // 重做
    const redoRes = useElementEditorStore.getState().redo();
    expect(redoRes).toBe(true);
    expect(useElementEditorStore.getState().currentSnapshotIndex).toBe(1);
  });

  it('rollbackToVersion 应直接回滚到指定版本号', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    useElementEditorStore.getState().applyMicroPatch('版本2修改', 'style');
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    useElementEditorStore.getState().applyMicroPatch('版本3修改', 'content');

    expect(useElementEditorStore.getState().snapshots.length).toBe(3);

    // 回滚到 v1
    useElementEditorStore.getState().rollbackToVersion(1);
    expect(useElementEditorStore.getState().currentSnapshotIndex).toBe(0);
  });
});
