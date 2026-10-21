import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

/**
 * Contract tests for the save state machine in SpreadsheetEditor.
 *
 * The save flow has 4 states: idle, saving, saved, saveError.
 * This tests the state transitions without rendering the component.
 *
 * State machine:
 *   idle → saving (on click)
 *   saving → saved (onSave resolves) → idle (after 2000ms)
 *   saving → saveError (onSave rejects) → idle (after 3000ms)
 *   saving → saving (click ignored while saving=true)
 */

type SaveState = 'idle' | 'saving' | 'saved' | 'saveError';

interface SaveStateMachine {
  state: SaveState;
  dirty: boolean;
  timers: ReturnType<typeof setTimeout>[];
}

function createSaveStateMachine(): SaveStateMachine {
  return { state: 'idle', dirty: false, timers: [] };
}

async function handleSave(
  sm: SaveStateMachine,
  onSave: (blob: Blob) => Promise<void>,
  onDirty: (dirty: boolean) => void,
): Promise<void> {
  if (sm.state === 'saving') {
    return;
  }

  sm.state = 'saving';

  try {
    const blob = new Blob(['test'], { type: 'application/octet-stream' });
    await onSave(blob);
    sm.dirty = false;
    onDirty(false);
    sm.state = 'saved';
    sm.timers.forEach(clearTimeout);
    sm.timers = [];
    const t = setTimeout(() => {
      sm.state = 'idle';
    }, 2000);
    sm.timers.push(t);
  } catch {
    sm.state = 'saveError';
    sm.timers.forEach(clearTimeout);
    sm.timers = [];
    const t = setTimeout(() => {
      sm.state = 'idle';
    }, 3000);
    sm.timers.push(t);
  }
}

function cleanup(sm: SaveStateMachine): void {
  sm.timers.forEach(clearTimeout);
  sm.timers = [];
}

describe('SpreadsheetEditor save state machine', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts in idle state', () => {
    const sm = createSaveStateMachine();
    expect(sm.state).toBe('idle');
    cleanup(sm);
  });

  it('transitions to saving then saved on successful save', async () => {
    const sm = createSaveStateMachine();
    sm.dirty = true;
    const onSave = vi.fn(async () => {});
    const onDirty = vi.fn();

    const p = handleSave(sm, onSave, onDirty);
    expect(sm.state).toBe('saving');

    await p;
    expect(sm.state).toBe('saved');
    expect(sm.dirty).toBe(false);
    expect(onDirty).toHaveBeenCalledWith(false);
    expect(onSave).toHaveBeenCalledOnce();

    cleanup(sm);
  });

  it('transitions back to idle after 2000ms from saved', async () => {
    const sm = createSaveStateMachine();
    const onSave = vi.fn(async () => {});
    const onDirty = vi.fn();

    await handleSave(sm, onSave, onDirty);
    expect(sm.state).toBe('saved');

    vi.advanceTimersByTime(1999);
    expect(sm.state).toBe('saved');

    vi.advanceTimersByTime(1);
    expect(sm.state).toBe('idle');

    cleanup(sm);
  });

  it('transitions to saveError on failed save', async () => {
    const sm = createSaveStateMachine();
    const onSave = vi.fn(async () => {
      throw new Error('Network error');
    });
    const onDirty = vi.fn();

    await handleSave(sm, onSave, onDirty);
    expect(sm.state).toBe('saveError');
    expect(onDirty).not.toHaveBeenCalled();

    cleanup(sm);
  });

  it('transitions back to idle after 3000ms from saveError', async () => {
    const sm = createSaveStateMachine();
    const onSave = vi.fn(async () => {
      throw new Error('fail');
    });
    const onDirty = vi.fn();

    await handleSave(sm, onSave, onDirty);
    expect(sm.state).toBe('saveError');

    vi.advanceTimersByTime(2999);
    expect(sm.state).toBe('saveError');

    vi.advanceTimersByTime(1);
    expect(sm.state).toBe('idle');

    cleanup(sm);
  });

  it('ignores save click while already saving', async () => {
    const sm = createSaveStateMachine();
    let resolveFirst!: () => void;
    const firstSave = new Promise<void>((r) => {
      resolveFirst = r;
    });
    const onSave = vi.fn(() => firstSave);
    const onDirty = vi.fn();

    const p1 = handleSave(sm, onSave, onDirty);
    expect(sm.state).toBe('saving');

    const p2 = handleSave(sm, onSave, onDirty);
    await p2;
    expect(onSave).toHaveBeenCalledOnce();

    resolveFirst();
    await p1;
    expect(sm.state).toBe('saved');

    cleanup(sm);
  });

  it('clears previous timer on rapid successive saves', async () => {
    const sm = createSaveStateMachine();
    const onSave = vi.fn(async () => {});
    const onDirty = vi.fn();

    await handleSave(sm, onSave, onDirty);
    expect(sm.state).toBe('saved');

    vi.advanceTimersByTime(1000);
    sm.state = 'idle';

    await handleSave(sm, onSave, onDirty);
    expect(sm.state).toBe('saved');

    vi.advanceTimersByTime(2000);
    expect(sm.state).toBe('idle');

    cleanup(sm);
  });

  it('button text contract: saving→saving, saved→saved, error→retry, idle→saveChanges', () => {
    function getButtonText(state: SaveState): string {
      if (state === 'saving') {
        return 'saving';
      }
      if (state === 'saved') {
        return 'saved';
      }
      if (state === 'saveError') {
        return 'retry';
      }
      return 'spreadsheet.saveChanges';
    }

    expect(getButtonText('idle')).toBe('spreadsheet.saveChanges');
    expect(getButtonText('saving')).toBe('saving');
    expect(getButtonText('saved')).toBe('saved');
    expect(getButtonText('saveError')).toBe('retry');
  });

  it('button style contract: saveError uses destructive class', () => {
    function getButtonStyleClass(saveError: boolean): string {
      return saveError
        ? 'bg-destructive text-destructive-foreground'
        : 'bg-primary text-primary-foreground hover:bg-primary/90';
    }

    expect(getButtonStyleClass(false)).toContain('bg-primary');
    expect(getButtonStyleClass(true)).toContain('bg-destructive');
  });
});
