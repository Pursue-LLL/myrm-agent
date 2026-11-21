import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSpeakingRowStore } from '../useSpeakingRowStore';

const { claim, release } = useSpeakingRowStore.getState();
const speakingRow = () => useSpeakingRowStore.getState().rowIndex;

beforeEach(() => {
  useSpeakingRowStore.setState({ rowIndex: null });
});

describe('useSpeakingRowStore', () => {
  it('starts with no speaking row', () => {
    expect(speakingRow()).toBeNull();
  });

  it('names the row that claims the speech', () => {
    claim(4);

    expect(speakingRow()).toBe(4);
  });

  it('hands the claim to the row that claims next', () => {
    claim(4);
    claim(9);

    expect(speakingRow()).toBe(9);
  });

  it('clears the claim when the row that holds it releases', () => {
    claim(4);
    release(4);

    expect(speakingRow()).toBeNull();
  });

  it('keeps the new speaker when the row it replaced winds down', () => {
    claim(4);
    claim(9);
    release(4);

    expect(speakingRow()).toBe(9);
  });

  it('does not notify subscribers when a release changes nothing', () => {
    const listener = vi.fn();
    const unsubscribe = useSpeakingRowStore.subscribe(listener);

    release(4);
    claim(9);
    release(4);

    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
});
