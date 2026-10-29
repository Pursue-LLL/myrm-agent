import { describe, it, expect, beforeEach } from 'vitest';
import { useWysiwygEditorStore } from '../useWysiwygEditorStore';
import { SelectedDomElementInfo } from '../wysiwygEditorTypes';

describe('useWysiwygEditorStore', () => {
  beforeEach(() => {
    useWysiwygEditorStore.getState().reset();
  });

  const sampleHtml =
    '<article><h2 class="title">数据大屏</h2><p>今日成交量 12,000</p></article>';

  it('初始状态处于预览模式且版本号为 1', () => {
    const state = useWysiwygEditorStore.getState();
    expect(state.mode).toBe('preview');
    expect(state.version).toBe(1);
    expect(state.selectedElement).toBeNull();
    expect(state.pendingMutations).toEqual([]);
    expect(state.lastCommitReport).toBeNull();
  });

  it('loadHtml 能够正确载入初始 HTML 并初始化状态', () => {
    const store = useWysiwygEditorStore.getState();
    store.loadHtml(sampleHtml);

    const state = useWysiwygEditorStore.getState();
    expect(state.originalHtml).toBe(sampleHtml);
    expect(state.currentHtml).toBe(sampleHtml);
    expect(state.mode).toBe('preview');
  });

  it('toggleEditMode 能够在 preview 与 editing 之间切换，并在退出时清除选中态', () => {
    const store = useWysiwygEditorStore.getState();
    store.toggleEditMode(true);
    expect(useWysiwygEditorStore.getState().mode).toBe('editing');

    // 选中元素
    const el: SelectedDomElementInfo = {
      selector: 'h2.title',
      tagName: 'H2',
      textContent: '数据大屏',
      styles: {},
    };
    store.selectElement(el);
    expect(useWysiwygEditorStore.getState().selectedElement).not.toBeNull();

    // 切换回预览模式
    store.toggleEditMode(false);
    expect(useWysiwygEditorStore.getState().mode).toBe('preview');
    expect(useWysiwygEditorStore.getState().selectedElement).toBeNull();
  });

  it('updateSelectedText 能够就地修改文本、更新 currentHtml 并记录变更', () => {
    const store = useWysiwygEditorStore.getState();
    store.loadHtml(sampleHtml);
    store.toggleEditMode(true);

    const el: SelectedDomElementInfo = {
      selector: 'h2.title',
      tagName: 'H2',
      textContent: '数据大屏',
      styles: {},
    };
    store.selectElement(el);

    store.updateSelectedText('实时电商数据大屏');

    const state = useWysiwygEditorStore.getState();
    expect(state.selectedElement?.textContent).toBe('实时电商数据大屏');
    expect(state.currentHtml).toContain('实时电商数据大屏');
    expect(state.pendingMutations).toHaveLength(1);
    expect(state.pendingMutations[0].changeType).toBe('text');
  });

  it('updateSelectedStyle 能够更新元素样式并记录变更', () => {
    const store = useWysiwygEditorStore.getState();
    store.loadHtml(sampleHtml);
    store.toggleEditMode(true);

    const el: SelectedDomElementInfo = {
      selector: 'h2.title',
      tagName: 'H2',
      textContent: '数据大屏',
      styles: { color: '#ffffff' },
    };
    store.selectElement(el);

    store.updateSelectedStyle({ color: '#6366f1', fontSize: '18px' });

    const state = useWysiwygEditorStore.getState();
    expect(state.selectedElement?.styles.color).toBe('#6366f1');
    expect(state.selectedElement?.styles.fontSize).toBe('18px');
    expect(state.pendingMutations).toHaveLength(1);
    expect(state.pendingMutations[0].changeType).toBe('style');
  });

  it('commitZeroTokenSave 能够递增版本、生成保存报告并同步 originalHtml', () => {
    const store = useWysiwygEditorStore.getState();
    store.loadHtml(sampleHtml);
    store.toggleEditMode(true);

    const el: SelectedDomElementInfo = {
      selector: 'h2.title',
      tagName: 'H2',
      textContent: '数据大屏',
      styles: {},
    };
    store.selectElement(el);
    store.updateSelectedText('全新大屏');

    const report = store.commitZeroTokenSave();

    const state = useWysiwygEditorStore.getState();
    expect(state.version).toBe(2);
    expect(state.mode).toBe('preview');
    expect(state.pendingMutations).toHaveLength(0);
    expect(state.originalHtml).toBe(state.currentHtml);
    expect(report.version).toBe(2);
    expect(report.mutationCount).toBe(1);
  });

  it('discardChanges 能够放弃所有修改并回退到 originalHtml', () => {
    const store = useWysiwygEditorStore.getState();
    store.loadHtml(sampleHtml);
    store.toggleEditMode(true);

    const el: SelectedDomElementInfo = {
      selector: 'h2.title',
      tagName: 'H2',
      textContent: '数据大屏',
      styles: {},
    };
    store.selectElement(el);
    store.updateSelectedText('被修改的标题');

    expect(useWysiwygEditorStore.getState().pendingMutations).toHaveLength(1);

    store.discardChanges();

    const state = useWysiwygEditorStore.getState();
    expect(state.currentHtml).toBe(sampleHtml);
    expect(state.pendingMutations).toHaveLength(0);
    expect(state.selectedElement).toBeNull();
  });
});
