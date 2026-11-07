import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Project } from '@/services/projects';
import { useProjectStore } from '@/store/useProjectStore';
import { contrastRatio } from '@/theme-engine';
import ProjectBar from '../ProjectBar';
import { PROJECT_COLORS } from '../ProjectContextMenu';

vi.mock('@/services/projects', () => ({
  getProjects: vi.fn(),
  createProject: vi.fn(),
  adoptProjectWorkspace: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
}));
vi.mock('@/components/features/project-workspace/ProjectWorkspaceMount', () => ({ default: () => null }));
vi.mock('@/components/features/project-workspace/ProjectWorkspaceAdoptDialog', () => ({ default: () => null }));
vi.mock('../ProjectDefaultAgentDialog', () => ({ ProjectDefaultAgentDialog: () => null }));

const makeProject = (id: string, name: string, color: string): Project => ({
  id,
  name,
  description: '',
  color,
  sortOrder: 0,
  goalSummary: '',
  createdAt: null,
  updatedAt: null,
});

const seed = (projects: Project[], activeFilter: string | null | undefined = undefined) =>
  useProjectStore.setState({ projects, activeFilter, loaded: true });

const chip = (name: string) => screen.getByRole('button', { name });

/** The `h-N` and `size-N` utilities are N × 4px, which is how every control states its target. */
const targetPx = (element: HTMLElement, axis: 'h' | 'size' = 'h') => {
  const match = new RegExp(`(?:^|\\s)${axis}-(\\d+)(?:\\s|$)`).exec(element.className);
  if (!match) {
    throw new Error(`no ${axis}-N class on <${element.tagName.toLowerCase()} class="${element.className}">`);
  }
  return Number(match[1]) * 4;
};

/** jsdom serializes inline hex colors as `rgb(r, g, b)`. */
const rgbToHex = (rgb: string) =>
  `#${(rgb.match(/\d+/g) ?? []).map((value) => Number(value).toString(16).padStart(2, '0')).join('')}`;

const TINY_TEXT = /text-\[(?:9|10)px\]/;

beforeEach(() => {
  localStorage.clear();
  seed([makeProject('p1', 'Atlas', '#7cb9ff')]);
});

describe('ProjectBar chip text', () => {
  it('sets chips at 11px on a pointer device and 12px on a phone, never below 11px', () => {
    const desktop = render(<ProjectBar isMobile={false} />);
    expect(chip('Atlas').className).toContain('text-[11px]');
    expect(chip('Atlas').className).not.toMatch(TINY_TEXT);
    desktop.unmount();

    render(<ProjectBar isMobile />);
    expect(chip('Atlas').className).toContain('text-xs');
    expect(chip('Atlas').className).not.toMatch(TINY_TEXT);
  });

  it('writes an unselected chip in the full muted text color, not a faded one', () => {
    render(<ProjectBar />);

    const { className } = chip('Atlas');
    expect(className).toContain('text-muted-foreground');
    expect(className).not.toMatch(/text-muted-foreground\//);
  });

  it('keeps the dark text of the accent chip for All and Unassigned', () => {
    render(<ProjectBar />);

    expect(chip('project.all').className).toContain('text-[var(--accent-warm-foreground)]');
    expect(chip('project.all').style.backgroundColor).toBe('var(--accent-warm)');
    expect(chip('project.unassigned').className).not.toContain('text-[var(--accent-warm-foreground)]');
  });

  it.each(PROJECT_COLORS)('keeps the selected chip readable on the palette color %s', (color) => {
    seed([makeProject('p1', 'Atlas', color)], 'p1');
    render(<ProjectBar />);

    const { style } = chip('Atlas');
    expect(rgbToHex(style.backgroundColor)).toBe(color);
    expect(contrastRatio(rgbToHex(style.color), color)).toBeGreaterThanOrEqual(4.5);
  });

  it('switches to light text on a dark project color', () => {
    seed([makeProject('p1', 'Atlas', '#1d4ed8')], 'p1');
    render(<ProjectBar />);

    const { style } = chip('Atlas');
    expect(contrastRatio(rgbToHex(style.color), '#1d4ed8')).toBeGreaterThanOrEqual(4.5);
    expect(rgbToHex(style.color)).not.toBe('#0a0a0a');
  });

  it('draws the color dot only while the chip is unselected', () => {
    const { container, rerender } = render(<ProjectBar />);
    expect(container.querySelector('span[style]')).not.toBeNull();

    seed([makeProject('p1', 'Atlas', '#7cb9ff')], 'p1');
    rerender(<ProjectBar />);
    expect(container.querySelector('span[style]')).toBeNull();
  });
});

describe('ProjectBar chip state', () => {
  it('reports the chosen filter to a screen reader', () => {
    seed([makeProject('p1', 'Atlas', '#7cb9ff')]);
    render(<ProjectBar />);

    expect(chip('project.all')).toHaveAttribute('aria-pressed', 'true');
    expect(chip('Atlas')).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(chip('Atlas'));

    expect(chip('Atlas')).toHaveAttribute('aria-pressed', 'true');
    expect(chip('project.all')).toHaveAttribute('aria-pressed', 'false');
    expect(chip('project.unassigned')).toHaveAttribute('aria-pressed', 'false');
  });
});

describe('ProjectBar chip targets', () => {
  it('keeps every chip and button at least 24px on a pointer device', () => {
    render(<ProjectBar isMobile={false} />);

    for (const name of ['project.all', 'project.unassigned', 'Atlas']) {
      expect(targetPx(chip(name))).toBeGreaterThanOrEqual(24);
    }
    expect(targetPx(screen.getByTitle('project.newProject'), 'size')).toBeGreaterThanOrEqual(24);
    expect(targetPx(screen.getByTitle('project.workspaceMount.adoptFolder'), 'size')).toBeGreaterThanOrEqual(24);
  });

  it('gives a phone finger-sized chips and buttons', () => {
    render(<ProjectBar isMobile />);

    for (const name of ['project.all', 'project.unassigned', 'Atlas']) {
      expect(targetPx(chip(name))).toBeGreaterThanOrEqual(40);
    }
    expect(targetPx(screen.getByTitle('project.newProject'), 'size')).toBeGreaterThanOrEqual(40);
    expect(targetPx(screen.getByTitle('project.workspaceMount.adoptFolder'), 'size')).toBeGreaterThanOrEqual(40);
  });

  it('draws the add and folder icons in the full muted color and larger on a phone', () => {
    const desktop = render(<ProjectBar isMobile={false} />);
    const add = screen.getByTitle('project.newProject');
    expect(add.className).toContain('text-muted-foreground');
    expect(add.className).not.toMatch(/text-muted-foreground\//);
    expect(add.querySelector('svg')).toHaveAttribute('width', '14');
    desktop.unmount();

    render(<ProjectBar isMobile />);
    expect(screen.getByTitle('project.workspaceMount.adoptFolder').querySelector('svg')).toHaveAttribute('width', '18');
  });

  it('sizes the first-project button for a finger on a phone and keeps the touch-screen step on wide layouts', () => {
    seed([]);
    const desktop = render(<ProjectBar isMobile={false} />);
    expect(screen.getByRole('button', { name: 'project.addFirst' }).className).toContain('h-6');
    expect(screen.getByRole('button', { name: 'project.addFirst' }).className).toContain('pointer-coarse:h-8');
    desktop.unmount();

    render(<ProjectBar isMobile />);
    expect(targetPx(screen.getByRole('button', { name: 'project.addFirst' }))).toBeGreaterThanOrEqual(40);
  });
});

describe('ProjectBar long names', () => {
  const longName = 'Quarterly-Roadmap-And-Release-Planning-Workspace-International-2026';

  it('truncates a chip to the width of the bar and keeps the full name as its tooltip', () => {
    seed([makeProject('p1', longName, '#7cb9ff')]);
    render(<ProjectBar />);

    const long = chip(longName);
    expect(long).toHaveClass('max-w-full', 'truncate');
    expect(long).toHaveAttribute('title', longName);
  });
});

describe('ProjectBar name fields', () => {
  const openRename = () => {
    fireEvent.contextMenu(chip('Atlas'), { clientX: 30, clientY: 40 });
    fireEvent.click(chip('project.rename'));
    return screen.getByDisplayValue('Atlas');
  };
  const openNew = () => {
    fireEvent.click(screen.getByTitle('project.newProject'));
    return screen.getByPlaceholderText('project.namePlaceholder');
  };

  it.each([
    ['new project', openNew],
    ['rename', openRename],
  ])('matches the chip height and types at 11px on a pointer device (%s)', (_name, open) => {
    render(<ProjectBar isMobile={false} />);

    const input = open();
    expect(targetPx(input)).toBe(24);
    expect(input.className).toContain('text-[11px]');
    expect(input.className).not.toMatch(/(?:^|\s)text-(?:xs|base)(?:\s|$)/);
  });

  it.each([
    ['new project', openNew],
    ['rename', openRename],
  ])('types at 16px and fits a finger on a phone so the keyboard does not zoom the page (%s)', (_name, open) => {
    render(<ProjectBar isMobile />);

    const input = open();
    expect(targetPx(input)).toBe(40);
    expect(input.className).toContain('text-base');
    expect(input.className).not.toMatch(TINY_TEXT);
  });

  it('writes the placeholder in the full muted text color and never wider than the bar', () => {
    render(<ProjectBar />);

    const { className } = openNew();
    expect(className).toContain('placeholder:text-muted-foreground');
    expect(className).not.toMatch(/placeholder:text-muted-foreground\//);
    expect(className).toContain('max-w-full');
  });
});

describe('ProjectBar context menu', () => {
  const openMenu = (x = 30, y = 40) => {
    fireEvent.contextMenu(chip('Atlas'), { clientX: x, clientY: y });
    return screen.getByRole('button', { name: 'project.rename' }).parentElement as HTMLElement;
  };

  it('makes the palette swatches 24px targets on a pointer device and 40px on a phone', () => {
    const desktop = render(<ProjectBar isMobile={false} />);
    openMenu();
    expect(targetPx(chip(PROJECT_COLORS[0] as string), 'size')).toBe(24);
    desktop.unmount();

    render(<ProjectBar isMobile />);
    openMenu();
    expect(targetPx(chip(PROJECT_COLORS[0] as string), 'size')).toBe(40);
  });

  it('lays the palette out in five columns so the menu stays narrow', () => {
    render(<ProjectBar />);

    const palette = openMenu().querySelector('div.grid');
    expect(palette).toHaveClass('grid-cols-5');
    expect(palette?.querySelectorAll('button')).toHaveLength(PROJECT_COLORS.length);
  });

  it('takes the width of its content so opening near the right edge cannot squeeze the palette', () => {
    render(<ProjectBar />);

    expect(openMenu(340, 40)).toHaveClass('w-max');
  });

  it('keeps the menu rows at 28px on a pointer device and raises them to 44px on a phone', () => {
    const desktop = render(<ProjectBar isMobile={false} />);
    openMenu();
    expect(chip('project.rename').className).toContain('py-1.5');
    expect(chip('project.rename').className).not.toContain('min-h-11');
    desktop.unmount();

    render(<ProjectBar isMobile />);
    openMenu();
    for (const name of ['project.rename', 'project.setWorkspace', 'project.setDefaultAgent', 'project.delete']) {
      expect(chip(name).className).toContain('min-h-11');
    }
  });

  it('opens at the pointer and pulls itself back inside the viewport on the right and bottom edges', () => {
    render(<ProjectBar />);

    const menu = openMenu(340, 700);

    expect(menu.style.left).toBe('340px');
    expect(menu.style.top).toBe('700px');
    // jsdom has no layout; the real clamp is measured in the browser. Here: both axes are guarded by `min(0px, …)`
    // against the viewport, and the offsets carry the pointer position plus the 8px gap.
    const { transform } = menu.style;
    expect(transform.match(/min\(0px,/g)).toHaveLength(2);
    expect(transform).toContain('100vw');
    expect(transform).toContain('100dvh');
    expect(transform).toContain('348px');
    expect(transform).toContain('708px');
  });
});
