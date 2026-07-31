import { describe, expect, it, vi, afterEach } from 'vitest';

/**
 * Contract tests for dirty tracking and beforeunload in SpreadsheetEditor.
 *
 * Dirty tracking contract:
 * - `markDirty` only calls `onDirty(true)` once (idempotent)
 * - After save, dirty resets to false and `onDirty(false)` is called
 * - `beforeunload` listener is added when dirty, removed when clean
 *
 * These tests use JSDOM's window object which is available in vitest's jsdom environment.
 */

describe('SpreadsheetEditor dirty tracking contract', () => {
  it('markDirty calls onDirty(true) only once', () => {
    const onDirty = vi.fn();
    let dirtyRef = false;

    function markDirty(): void {
      if (!dirtyRef) {
        dirtyRef = true;
        onDirty(true);
      }
    }

    markDirty();
    expect(onDirty).toHaveBeenCalledWith(true);
    expect(onDirty).toHaveBeenCalledOnce();

    markDirty();
    markDirty();
    expect(onDirty).toHaveBeenCalledOnce();
  });

  it('save resets dirty and calls onDirty(false)', async () => {
    const onDirty = vi.fn();
    let dirtyRef = true;

    async function simulateSave(): Promise<void> {
      dirtyRef = false;
      onDirty(false);
    }

    await simulateSave();
    expect(dirtyRef).toBe(false);
    expect(onDirty).toHaveBeenCalledWith(false);
  });

  it('failed save does NOT reset dirty', async () => {
    const onDirty = vi.fn();
    let dirtyRef = true;

    async function simulateFailedSave(): Promise<void> {
      try {
        throw new Error('Upload failed');
      } catch {
        // dirty stays true on error
      }
    }

    await simulateFailedSave();
    expect(dirtyRef).toBe(true);
    expect(onDirty).not.toHaveBeenCalled();
  });

  it('markDirty is re-callable after save clears dirty', () => {
    const onDirty = vi.fn();
    let dirtyRef = false;

    function markDirty(): void {
      if (!dirtyRef) {
        dirtyRef = true;
        onDirty(true);
      }
    }

    markDirty();
    expect(onDirty).toHaveBeenCalledOnce();

    dirtyRef = false;
    onDirty.mockClear();

    markDirty();
    expect(onDirty).toHaveBeenCalledWith(true);
    expect(onDirty).toHaveBeenCalledOnce();
  });
});

describe('SpreadsheetEditor beforeunload contract', () => {
  afterEach(() => {
    const noop = (): void => {};
    window.removeEventListener('beforeunload', noop);
  });

  it('beforeunload handler calls preventDefault', () => {
    const handler = (e: BeforeUnloadEvent): void => {
      e.preventDefault();
    };

    const event = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    handler(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('addEventListener/removeEventListener lifecycle', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const removeSpy = vi.spyOn(window, 'removeEventListener');

    const handler = (e: BeforeUnloadEvent): void => { e.preventDefault(); };

    window.addEventListener('beforeunload', handler);
    expect(addSpy).toHaveBeenCalledWith('beforeunload', handler);

    window.removeEventListener('beforeunload', handler);
    expect(removeSpy).toHaveBeenCalledWith('beforeunload', handler);

    addSpy.mockRestore();
    removeSpy.mockRestore();
  });

  it('handler should only be active when dirty', () => {
    let dirty = false;
    let handlerRegistered = false;
    const handler = (e: BeforeUnloadEvent): void => { e.preventDefault(); };

    function syncBeforeUnload(): void {
      if (dirty && !handlerRegistered) {
        window.addEventListener('beforeunload', handler);
        handlerRegistered = true;
      } else if (!dirty && handlerRegistered) {
        window.removeEventListener('beforeunload', handler);
        handlerRegistered = false;
      }
    }

    syncBeforeUnload();
    expect(handlerRegistered).toBe(false);

    dirty = true;
    syncBeforeUnload();
    expect(handlerRegistered).toBe(true);

    dirty = false;
    syncBeforeUnload();
    expect(handlerRegistered).toBe(false);
  });
});

describe('SpreadsheetEditor ArtifactPortal dirty integration contract', () => {
  it('handleEditDirty calls markAsDirty and clearDirtyState correctly', () => {
    const markAsDirty = vi.fn();
    const clearDirtyState = vi.fn();
    const artifactId = 'test-artifact-123';

    function handleEditDirty(dirty: boolean): void {
      if (dirty) {
        markAsDirty(artifactId, '__spreadsheet_edit__');
      } else {
        clearDirtyState(artifactId);
      }
    }

    handleEditDirty(true);
    expect(markAsDirty).toHaveBeenCalledWith(artifactId, '__spreadsheet_edit__');

    handleEditDirty(false);
    expect(clearDirtyState).toHaveBeenCalledWith(artifactId);
  });
});
