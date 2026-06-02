import { renderHook, act } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useAnnotationState } from '../hooks/useAnnotationState';
import type { ArrowAnnotation } from '../types';

function makeArrow(id: string): ArrowAnnotation {
  return {
    id,
    tool: 'arrow',
    color: '#ef4444',
    strokeWidth: 4,
    start: { x: 10, y: 10 },
    end: { x: 100, y: 100 },
  };
}

describe('useAnnotationState', () => {
  it('initializes with empty annotations and default values', () => {
    const { result } = renderHook(() => useAnnotationState());
    expect(result.current.annotations).toEqual([]);
    expect(result.current.activeTool).toBe('arrow');
    expect(result.current.activeColor).toBe('#ef4444');
    expect(result.current.strokeWidth).toBe(4);
    expect(result.current.fontSize).toBe(18);
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
  });

  it('adds annotations and enables undo', () => {
    const { result } = renderHook(() => useAnnotationState());
    const arrow = makeArrow('a1');

    act(() => result.current.addAnnotation(arrow));

    expect(result.current.annotations).toHaveLength(1);
    expect(result.current.annotations[0]).toEqual(arrow);
    expect(result.current.canUndo).toBe(true);
    expect(result.current.canRedo).toBe(false);
  });

  it('undo removes the last annotation and enables redo', () => {
    const { result } = renderHook(() => useAnnotationState());
    const a1 = makeArrow('a1');
    const a2 = makeArrow('a2');

    act(() => result.current.addAnnotation(a1));
    act(() => result.current.addAnnotation(a2));
    expect(result.current.annotations).toHaveLength(2);

    act(() => result.current.undo());
    expect(result.current.annotations).toHaveLength(1);
    expect(result.current.annotations[0].id).toBe('a1');
    expect(result.current.canUndo).toBe(true);
    expect(result.current.canRedo).toBe(true);
  });

  it('redo restores the undone annotation', () => {
    const { result } = renderHook(() => useAnnotationState());
    const a1 = makeArrow('a1');

    act(() => result.current.addAnnotation(a1));
    act(() => result.current.undo());
    expect(result.current.annotations).toHaveLength(0);

    act(() => result.current.redo());
    expect(result.current.annotations).toHaveLength(1);
    expect(result.current.annotations[0].id).toBe('a1');
    expect(result.current.canRedo).toBe(false);
  });

  it('clearAll empties annotations and allows undo', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.addAnnotation(makeArrow('a1')));
    act(() => result.current.addAnnotation(makeArrow('a2')));
    act(() => result.current.clearAll());

    expect(result.current.annotations).toHaveLength(0);
    expect(result.current.canUndo).toBe(true);
  });

  it('adding after undo clears redo stack', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.addAnnotation(makeArrow('a1')));
    act(() => result.current.undo());
    expect(result.current.canRedo).toBe(true);

    act(() => result.current.addAnnotation(makeArrow('a2')));
    expect(result.current.canRedo).toBe(false);
    expect(result.current.annotations).toHaveLength(1);
    expect(result.current.annotations[0].id).toBe('a2');
  });

  it('setActiveTool changes the active tool', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.setActiveTool('text'));
    expect(result.current.activeTool).toBe('text');
  });

  it('setActiveColor changes the active color', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.setActiveColor('#3b82f6'));
    expect(result.current.activeColor).toBe('#3b82f6');
  });

  it('setStrokeWidth changes stroke width', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.setStrokeWidth(8));
    expect(result.current.strokeWidth).toBe(8);
  });

  it('removeAnnotation removes by id', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.addAnnotation(makeArrow('a1')));
    act(() => result.current.addAnnotation(makeArrow('a2')));
    act(() => result.current.removeAnnotation('a1'));

    expect(result.current.annotations).toHaveLength(1);
    expect(result.current.annotations[0].id).toBe('a2');
  });

  it('updateAnnotation modifies specific annotation', () => {
    const { result } = renderHook(() => useAnnotationState());
    const a1 = makeArrow('a1');

    act(() => result.current.addAnnotation(a1));
    act(() =>
      result.current.updateAnnotation('a1', (ann) => ({
        ...ann,
        color: '#000000',
      })),
    );

    expect(result.current.annotations[0].color).toBe('#000000');
  });

  it('undo on empty stack is no-op', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.undo());
    expect(result.current.annotations).toEqual([]);
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
  });

  it('redo on empty stack is no-op', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.redo());
    expect(result.current.annotations).toEqual([]);
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
  });

  it('multiple consecutive undos work correctly', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.addAnnotation(makeArrow('a1')));
    act(() => result.current.addAnnotation(makeArrow('a2')));
    act(() => result.current.addAnnotation(makeArrow('a3')));

    act(() => result.current.undo());
    act(() => result.current.undo());
    act(() => result.current.undo());

    expect(result.current.annotations).toHaveLength(0);
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(true);
  });

  it('multiple consecutive redos work correctly', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.addAnnotation(makeArrow('a1')));
    act(() => result.current.addAnnotation(makeArrow('a2')));
    act(() => result.current.undo());
    act(() => result.current.undo());

    act(() => result.current.redo());
    act(() => result.current.redo());

    expect(result.current.annotations).toHaveLength(2);
    expect(result.current.canRedo).toBe(false);
  });

  it('removeAnnotation with non-existent id is no-op', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.addAnnotation(makeArrow('a1')));
    act(() => result.current.removeAnnotation('nonexistent'));

    expect(result.current.annotations).toHaveLength(1);
  });

  it('updateAnnotation with non-existent id is no-op', () => {
    const { result } = renderHook(() => useAnnotationState());
    const a1 = makeArrow('a1');

    act(() => result.current.addAnnotation(a1));
    act(() =>
      result.current.updateAnnotation('nonexistent', (ann) => ({
        ...ann,
        color: '#000000',
      })),
    );

    expect(result.current.annotations[0].color).toBe('#ef4444');
  });

  it('clearAll on empty state is no-op', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.clearAll());

    expect(result.current.annotations).toHaveLength(0);
    expect(result.current.canUndo).toBe(false);
  });

  it('undo after clearAll restores all annotations', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.addAnnotation(makeArrow('a1')));
    act(() => result.current.addAnnotation(makeArrow('a2')));
    act(() => result.current.clearAll());
    act(() => result.current.undo());

    expect(result.current.annotations).toHaveLength(2);
  });

  it('rapid add-undo-add sequence maintains correct state', () => {
    const { result } = renderHook(() => useAnnotationState());

    act(() => result.current.addAnnotation(makeArrow('a1')));
    act(() => result.current.undo());
    act(() => result.current.addAnnotation(makeArrow('a2')));
    act(() => result.current.addAnnotation(makeArrow('a3')));
    act(() => result.current.undo());

    expect(result.current.annotations).toHaveLength(1);
    expect(result.current.annotations[0].id).toBe('a2');
    expect(result.current.canUndo).toBe(true);
    expect(result.current.canRedo).toBe(true);
  });
});
