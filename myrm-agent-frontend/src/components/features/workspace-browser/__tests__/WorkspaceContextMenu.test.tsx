/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileEntry } from '@/services/chat';
import { ContextMenu } from '../WorkspaceContextMenu';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const FILE: FileEntry = {
  name: 'Hello.ts',
  path: '/vault/chat-1/Hello.ts',
  type: 'file',
  size: 10,
  mtime: null,
  is_text: true,
  children: null,
};

const FOLDER: FileEntry = { ...FILE, name: 'src', path: '/vault/chat-1/src', type: 'directory', children: [] };

const MENU_SIZE = { width: 160, height: 100 };
const VIEWPORT = { width: 390, height: 844 };

function renderMenu(
  x: number,
  y: number,
  node: FileEntry = FILE,
  extra: Partial<Parameters<typeof ContextMenu>[0]> = {},
) {
  const handlers = { onClose: vi.fn(), onRename: vi.fn(), onDelete: vi.fn(), onMove: vi.fn() };
  const view = render(<ContextMenu state={{ x, y, node }} {...handlers} {...extra} />);
  const menu = screen.getByText('rename').closest('div') as HTMLElement;
  return { ...handlers, menu, view };
}

describe('ContextMenu', () => {
  beforeEach(() => {
    // jsdom lays nothing out: give the menu the size a browser would measure.
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(MENU_SIZE.width);
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(MENU_SIZE.height);
    Object.assign(window, { innerWidth: VIEWPORT.width, innerHeight: VIEWPORT.height });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens at the click when it fits in the viewport', () => {
    const { menu } = renderMenu(100, 200);

    expect(menu.style.left).toBe('100px');
    expect(menu.style.top).toBe('200px');
  });

  it('opens to the left of the click when it would run past the right edge', () => {
    const { menu } = renderMenu(300, 200);

    expect(menu.style.left).toBe('140px');
  });

  it('opens above the click when it would run past the bottom edge', () => {
    const { menu } = renderMenu(100, 800);

    expect(menu.style.top).toBe('700px');
  });

  it('runs the chosen action on its entry and closes', () => {
    const { onRename, onClose } = renderMenu(100, 200);

    fireEvent.click(screen.getByText('rename'));

    expect(onRename).toHaveBeenCalledWith(FILE);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('offers the folder-only actions for folders when the host provides them', () => {
    renderMenu(100, 200, FOLDER, { onOrganize: vi.fn(), onSetProjectRoot: vi.fn() });

    expect(screen.getByText('organizeFolder')).toBeDefined();
    expect(screen.getByText('setProjectRoot')).toBeDefined();
  });

  it('keeps the folder-only actions off a file', () => {
    renderMenu(100, 200, FILE, { onOrganize: vi.fn(), onSetProjectRoot: vi.fn() });

    expect(screen.queryByText('organizeFolder')).toBeNull();
    expect(screen.queryByText('setProjectRoot')).toBeNull();
  });
});
