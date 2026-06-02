'use client';

import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { MobileActionSheet, type MobileActionSheetEntry } from '../MobileActionSheet';

function makeEntries(overrides: Partial<MobileActionSheetEntry>[] = []): MobileActionSheetEntry[] {
  const defaults: MobileActionSheetEntry[] = [
    { key: 'model', label: 'Model', meta: 'gpt-4' },
    { key: 'thinking', label: 'Thinking', meta: 'high' },
  ];
  return overrides.length ? overrides.map((o, i) => ({ ...defaults[i % defaults.length], ...o })) : defaults;
}

describe('MobileActionSheet', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // Mounting / Unmounting
  // -----------------------------------------------------------------------

  it('does not render when open=false', () => {
    const { container } = render(<MobileActionSheet open={false} onClose={vi.fn()} entries={makeEntries()} />);
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it('renders dialog when open=true', async () => {
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('renders title when provided', async () => {
    render(<MobileActionSheet open={true} onClose={vi.fn()} title="Options" entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText('Options')).toBeInTheDocument();
  });

  it('unmounts after close transition', async () => {
    const onClose = vi.fn();
    const { rerender } = render(<MobileActionSheet open={true} onClose={onClose} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();

    rerender(<MobileActionSheet open={false} onClose={onClose} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(400);
    });
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  // -----------------------------------------------------------------------
  // Entry rendering
  // -----------------------------------------------------------------------

  it('renders all entries with data-testid', async () => {
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByTestId('mobile-action-sheet-model')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-action-sheet-thinking')).toBeInTheDocument();
  });

  it('renders entry icon when provided', async () => {
    const entries = makeEntries([{ key: 'a', label: 'A', icon: <span data-testid="icon-a">I</span> }]);
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByTestId('icon-a')).toBeInTheDocument();
  });

  it('renders entry description when provided', async () => {
    const entries = makeEntries([{ key: 'a', label: 'A', description: 'Desc text' }]);
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText('Desc text')).toBeInTheDocument();
  });

  it('renders divider before entry when dividerBefore=true', async () => {
    const entries: MobileActionSheetEntry[] = [
      { key: 'a', label: 'A' },
      { key: 'b', label: 'B', dividerBefore: true },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    const dialog = screen.getByRole('dialog');
    const dividers = dialog.querySelectorAll('.bg-muted');
    expect(dividers.length).toBeGreaterThanOrEqual(1);
  });

  it('does not render divider for first entry even with dividerBefore', async () => {
    const entries: MobileActionSheetEntry[] = [{ key: 'a', label: 'A', dividerBefore: true }];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    const dialog = screen.getByRole('dialog');
    const dividers = dialog.querySelectorAll('.h-\\[3px\\].bg-muted');
    expect(dividers).toHaveLength(0);
  });

  // -----------------------------------------------------------------------
  // Click & close behavior
  // -----------------------------------------------------------------------

  it('calls onClick and onClose when clicking entry without submenu', async () => {
    const onClose = vi.fn();
    const onClick = vi.fn();
    const entries = makeEntries([{ key: 'action', label: 'Action', onClick }]);
    render(<MobileActionSheet open={true} onClose={onClose} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-action'));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not fire onClick when entry is disabled', async () => {
    const onClick = vi.fn();
    const entries = makeEntries([{ key: 'd', label: 'Disabled', onClick, disabled: true }]);
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-d'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('closes when clicking backdrop', async () => {
    const onClose = vi.fn();
    render(<MobileActionSheet open={true} onClose={onClose} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    const backdrop = document.querySelector('.bg-black\\/40');
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not close when clicking inside the sheet', async () => {
    const onClose = vi.fn();
    render(<MobileActionSheet open={true} onClose={onClose} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
  });

  // -----------------------------------------------------------------------
  // Body scroll lock
  // -----------------------------------------------------------------------

  it('locks body scroll when open', async () => {
    const { rerender } = render(<MobileActionSheet open={true} onClose={vi.fn()} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(document.body.style.overflow).toBe('hidden');

    rerender(<MobileActionSheet open={false} onClose={vi.fn()} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  // -----------------------------------------------------------------------
  // Sub-menu navigation
  // -----------------------------------------------------------------------

  it('navigates to submenu on entry click', async () => {
    const onSelect = vi.fn();
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'model',
        label: 'Model',
        submenu: {
          title: 'Choose Model',
          options: [
            { key: 'gpt4', label: 'GPT-4', active: true },
            { key: 'claude', label: 'Claude', active: false },
          ],
          onSelect,
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-model'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText('Choose Model')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-action-sheet-option-gpt4')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-action-sheet-option-claude')).toBeInTheDocument();
  });

  it('calls submenu onSelect and goes back when selecting option (selectable=true)', async () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'model',
        label: 'Model',
        submenu: {
          title: 'Choose',
          options: [{ key: 'opt1', label: 'Option 1', active: false }],
          onSelect,
          selectable: true,
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={onClose} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-model'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-option-opt1'));
    expect(onSelect).toHaveBeenCalledWith('opt1');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose when selectable=false after selecting option', async () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'action',
        label: 'Actions',
        submenu: {
          title: 'Do',
          options: [{ key: 'run', label: 'Run' }],
          onSelect,
          selectable: false,
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={onClose} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-action'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-option-run'));
    expect(onSelect).toHaveBeenCalledWith('run');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('goes back to main menu via back button', async () => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'sub',
        label: 'Sub',
        submenu: {
          title: 'SubMenu',
          options: [{ key: 'x', label: 'X' }],
          onSelect: vi.fn(),
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-sub'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText('SubMenu')).toBeInTheDocument();

    fireEvent.click(screen.getByText('back'));
    // After clicking back, activeSubKey becomes null, sub pane unmounts
    expect(screen.queryByText('SubMenu')).toBeNull();
  });

  it('renders empty text when submenu has no options', async () => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'empty',
        label: 'Empty',
        submenu: {
          title: 'Nothing',
          options: [],
          onSelect: vi.fn(),
          emptyText: 'Nothing here',
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-empty'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
  });

  it('renders default noOptions text when emptyText is not provided', async () => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'empty2',
        label: 'Empty2',
        submenu: {
          title: 'NoOpts',
          options: [],
          onSelect: vi.fn(),
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-empty2'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText('noOptions')).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Radio indicator
  // -----------------------------------------------------------------------

  it('shows radio indicator for selectable submenu options', async () => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'r',
        label: 'R',
        submenu: {
          title: 'Radio',
          options: [
            { key: 'active', label: 'Active', active: true },
            { key: 'inactive', label: 'Inactive', active: false },
          ],
          onSelect: vi.fn(),
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-r'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    const radioIndicators = document.querySelectorAll('.rounded-full.border-\\[1\\.5px\\]');
    expect(radioIndicators.length).toBe(2);
    const activeRadio = document.querySelector('.border-primary.bg-primary');
    expect(activeRadio).not.toBeNull();
  });

  it('hides radio indicator when selectable=false', async () => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'nr',
        label: 'NR',
        submenu: {
          title: 'No Radio',
          options: [{ key: 'x', label: 'X', active: true }],
          onSelect: vi.fn(),
          selectable: false,
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-nr'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    const radioIndicators = document.querySelectorAll('.rounded-full.border-\\[1\\.5px\\]');
    expect(radioIndicators).toHaveLength(0);
  });

  // -----------------------------------------------------------------------
  // Accessibility
  // -----------------------------------------------------------------------

  it('has aria-modal=true on dialog', async () => {
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('marks main pane as aria-hidden when submenu is active', async () => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 's',
        label: 'S',
        submenu: { title: 'T', options: [{ key: 'o', label: 'O' }], onSelect: vi.fn() },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-s'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    const dialog = screen.getByRole('dialog');
    const mainPane = dialog.querySelector('[aria-hidden="true"]');
    expect(mainPane).not.toBeNull();
  });

  // -----------------------------------------------------------------------
  // Meta and chevron rendering
  // -----------------------------------------------------------------------

  it('renders meta text for entries', async () => {
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={makeEntries()} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText('gpt-4')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
  });

  it('renders chevron icon for entries with submenu', async () => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'withsub',
        label: 'With Sub',
        submenu: { title: 'S', options: [], onSelect: vi.fn() },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    const btn = screen.getByTestId('mobile-action-sheet-withsub');
    const svg = btn.querySelector('svg');
    expect(svg).not.toBeNull();
  });

  // -----------------------------------------------------------------------
  // Entry without onClick (no-op)
  // -----------------------------------------------------------------------

  it('does not throw when clicking entry without onClick or submenu', async () => {
    const onClose = vi.fn();
    const entries: MobileActionSheetEntry[] = [{ key: 'noop', label: 'NoOp' }];
    render(<MobileActionSheet open={true} onClose={onClose} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(() => {
      fireEvent.click(screen.getByTestId('mobile-action-sheet-noop'));
    }).not.toThrow();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  // -----------------------------------------------------------------------
  // Option description rendering
  // -----------------------------------------------------------------------

  it('renders option description in submenu', async () => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'desc',
        label: 'Desc',
        submenu: {
          title: 'T',
          options: [{ key: 'o', label: 'Opt', description: 'Option desc' }],
          onSelect: vi.fn(),
        },
      },
    ];
    render(<MobileActionSheet open={true} onClose={vi.fn()} entries={entries} />);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.click(screen.getByTestId('mobile-action-sheet-desc'));
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText('Option desc')).toBeInTheDocument();
  });
});
