import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useInfiniteCanvasStore } from '../useInfiniteCanvasStore';
import { TextLayer } from '../infiniteCanvasTypes';

describe('useInfiniteCanvasStore', () => {
  beforeEach(() => {
    useInfiniteCanvasStore.getState().resetCanvas();
  });

  it('initializes with default design layers and initial zero-token stats', () => {
    const state = useInfiniteCanvasStore.getState();
    expect(state.layers.length).toBeGreaterThanOrEqual(4);
    expect(state.toolMode).toBe('select');
    expect(state.viewport.zoom).toBe(1);
    expect(state.zeroTokenStats.inlineEditCount).toBe(0);
    expect(state.zeroTokenStats.estimatedSavedTokens).toBe(0);
  });

  it('updates tool mode and layer position', () => {
    const store = useInfiniteCanvasStore.getState();
    store.setToolMode('lasso');
    expect(useInfiniteCanvasStore.getState().toolMode).toBe('lasso');

    store.updateLayerPosition('layer_title', 120, 150);
    const updatedTitle = useInfiniteCanvasStore
      .getState()
      .layers.find((l) => l.id === 'layer_title');
    expect(updatedTitle?.x).toBe(120);
    expect(updatedTitle?.y).toBe(150);
  });

  it('performs zero-token inline text edit and accumulates savings counter', () => {
    const store = useInfiniteCanvasStore.getState();

    // 启动行内编辑
    store.startInlineTextEdit('layer_title');
    expect(useInfiniteCanvasStore.getState().editingTextLayerId).toBe('layer_title');

    // 完成免 Token 改字
    store.finishInlineTextEdit('2026 全球 AI 领袖峰会');

    const state = useInfiniteCanvasStore.getState();
    const updatedLayer = state.layers.find((l) => l.id === 'layer_title') as TextLayer;
    expect(updatedLayer.text).toBe('2026 全球 AI 领袖峰会');
    expect(state.editingTextLayerId).toBeNull();
    expect(state.zeroTokenStats.inlineEditCount).toBe(1);
    expect(state.zeroTokenStats.estimatedSavedTokens).toBe(2800);

    // 再次双击改字
    store.startInlineTextEdit('layer_desc');
    store.finishInlineTextEdit('免 Token 直编已节省两次！');

    const nextState = useInfiniteCanvasStore.getState();
    expect(nextState.zeroTokenStats.inlineEditCount).toBe(2);
    expect(nextState.zeroTokenStats.estimatedSavedTokens).toBe(5600);
  });

  it('cancels inline text edit without mutating text or saving stats', () => {
    const store = useInfiniteCanvasStore.getState();
    store.startInlineTextEdit('layer_title');
    store.cancelInlineTextEdit();

    const state = useInfiniteCanvasStore.getState();
    expect(state.editingTextLayerId).toBeNull();
    expect(state.zeroTokenStats.inlineEditCount).toBe(0);
  });

  it('controls canvas viewport zooming', () => {
    const store = useInfiniteCanvasStore.getState();

    store.zoomIn();
    expect(useInfiniteCanvasStore.getState().viewport.zoom).toBe(1.1);

    store.zoomOut();
    expect(useInfiniteCanvasStore.getState().viewport.zoom).toBe(1);

    store.setViewport({ zoom: 2, panX: 100 });
    expect(useInfiniteCanvasStore.getState().viewport.zoom).toBe(2);

    store.resetZoom();
    expect(useInfiniteCanvasStore.getState().viewport.zoom).toBe(1);
  });

  it('sets lasso box and dispatches inpainting context', () => {
    const store = useInfiniteCanvasStore.getState();
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    // 框选标题与底板区域
    store.setLassoBox({ startX: 60, startY: 60, endX: 300, endY: 150 });
    const inpaintContext = store.submitLassoInpainting('将标题改为渐变艺术字');

    expect(inpaintContext).not.toBeNull();
    expect(inpaintContext?.targetLayerIds).toContain('layer_title');
    expect(inpaintContext?.promptHint).toBe('将标题改为渐变艺术字');
    expect(dispatchSpy).toHaveBeenCalled();
  });

  it('adds and removes layers correctly', () => {
    const store = useInfiniteCanvasStore.getState();
    const newText: TextLayer = {
      id: 'layer_footer',
      name: '页脚',
      type: 'text',
      x: 100,
      y: 400,
      width: 200,
      height: 30,
      opacity: 1,
      isLocked: false,
      zIndex: 3,
      text: '版权所有 2026',
      fontSize: 12,
      fontWeight: '300',
      color: '#64748b',
      fontFamily: 'sans-serif',
    };

    store.addLayer(newText);
    expect(useInfiniteCanvasStore.getState().layers.some((l) => l.id === 'layer_footer')).toBe(true);
    expect(useInfiniteCanvasStore.getState().selectedLayerId).toBe('layer_footer');

    store.removeLayer('layer_footer');
    expect(useInfiniteCanvasStore.getState().layers.some((l) => l.id === 'layer_footer')).toBe(false);
  });
});
