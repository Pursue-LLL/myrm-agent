import { act } from '@testing-library/react';
import type { Range } from '@tanstack/react-virtual';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useSpeakingRowStore } from '@/store/useSpeakingRowStore';
import { installListStubs, kit, renderList, tearDownList } from './virtualListKit';

beforeEach(() => {
  installListStubs();
  useSpeakingRowStore.setState({ rowIndex: null });
});

afterEach(tearDownList);

/** Rows 10-12 are on screen; with the list's overscan of 3 the library renders rows 7-15. */
const onScreen: Range = { startIndex: 10, endIndex: 12, overscan: 3, count: 30 };
const WINDOW_ROWS = [7, 8, 9, 10, 11, 12, 13, 14, 15];

const rowsToRender = () => kit.state.options?.rangeExtractor(onScreen);

describe('VirtualMessageList speaking row', () => {
  it('renders just the window while nothing is read aloud', () => {
    renderList();

    expect(rowsToRender()).toEqual(WINDOW_ROWS);
  });

  it('keeps a speaking row below the window mounted, in index order', () => {
    useSpeakingRowStore.setState({ rowIndex: 25 });
    renderList();

    expect(rowsToRender()).toEqual([...WINDOW_ROWS, 25]);
  });

  it('keeps a speaking row above the window mounted, in index order', () => {
    useSpeakingRowStore.setState({ rowIndex: 2 });
    renderList();

    expect(rowsToRender()).toEqual([2, ...WINDOW_ROWS]);
  });

  it('does not repeat a speaking row that is already in the window', () => {
    useSpeakingRowStore.setState({ rowIndex: 11 });
    renderList();

    expect(rowsToRender()).toEqual(WINDOW_ROWS);
  });

  it('ignores a speaking row the list no longer has', () => {
    useSpeakingRowStore.setState({ rowIndex: 30 });
    renderList();

    expect(rowsToRender()).toEqual(WINDOW_ROWS);
  });

  it('follows the speaking row as it is claimed and released', () => {
    renderList();

    act(() => useSpeakingRowStore.getState().claim(25));
    expect(rowsToRender()).toEqual([...WINDOW_ROWS, 25]);

    act(() => useSpeakingRowStore.getState().release(25));
    expect(rowsToRender()).toEqual(WINDOW_ROWS);
  });

  it('hands the virtualizer the same extractor until the speaking row changes', () => {
    useSpeakingRowStore.setState({ rowIndex: 25 });
    const { update } = renderList();
    const extractor = kit.state.options?.rangeExtractor;

    update({ loading: true });
    expect(kit.state.options?.rangeExtractor).toBe(extractor);

    act(() => useSpeakingRowStore.getState().claim(26));
    expect(kit.state.options?.rangeExtractor).not.toBe(extractor);
  });
});
