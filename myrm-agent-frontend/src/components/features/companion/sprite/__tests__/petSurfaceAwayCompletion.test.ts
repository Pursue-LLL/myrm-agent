import { describe, expect, it, vi } from 'vitest';

import {
  dispatchPetSurfaceAwayCompletion,
  PET_SURFACE_AWAY_COMPLETION_EVENT,
} from '../petSurfaceAwayCompletion';

describe('petSurfaceAwayCompletion', () => {
  it('dispatches when document is hidden', () => {
    const handler = vi.fn();
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);
    window.addEventListener(PET_SURFACE_AWAY_COMPLETION_EVENT, handler);

    dispatchPetSurfaceAwayCompletion();

    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener(PET_SURFACE_AWAY_COMPLETION_EVENT, handler);
  });

  it('does not dispatch when page is focused and visible', () => {
    const handler = vi.fn();
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);
    window.addEventListener(PET_SURFACE_AWAY_COMPLETION_EVENT, handler);

    dispatchPetSurfaceAwayCompletion();

    expect(handler).not.toHaveBeenCalled();
    window.removeEventListener(PET_SURFACE_AWAY_COMPLETION_EVENT, handler);
  });
});
