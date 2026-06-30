import { describe, it, expect } from 'vitest';
import {
  PRESET_DEPENDENCIES,
  OPTIONAL_DEPENDENCIES,
  TAILWIND_CSS,
  CN_UTILS_CODE,
  TAILWIND_CONFIG,
} from '../reactPreviewConstants';

describe('PRESET_DEPENDENCIES', () => {
  it('includes essential UI libraries', () => {
    expect(PRESET_DEPENDENCIES).toHaveProperty('lucide-react');
    expect(PRESET_DEPENDENCIES).toHaveProperty('clsx');
    expect(PRESET_DEPENDENCIES).toHaveProperty('tailwind-merge');
    expect(PRESET_DEPENDENCIES).toHaveProperty('class-variance-authority');
  });

  it('includes charting library', () => {
    expect(PRESET_DEPENDENCIES).toHaveProperty('recharts');
  });

  it('includes animation library', () => {
    expect(PRESET_DEPENDENCIES).toHaveProperty('framer-motion');
  });

  it('includes date handling library', () => {
    expect(PRESET_DEPENDENCIES).toHaveProperty('date-fns');
  });

  it('includes state management', () => {
    expect(PRESET_DEPENDENCIES).toHaveProperty('zustand');
  });

  it('includes form handling', () => {
    expect(PRESET_DEPENDENCIES).toHaveProperty('react-hook-form');
  });

  it('has valid version strings for all entries', () => {
    for (const [pkg, version] of Object.entries(PRESET_DEPENDENCIES)) {
      expect(version, `${pkg} version should be a non-empty string`).toBeTruthy();
      expect(typeof version).toBe('string');
    }
  });
});

describe('OPTIONAL_DEPENDENCIES', () => {
  const RADIX_COMPONENTS = [
    'accordion', 'alert-dialog', 'avatar', 'checkbox', 'collapsible',
    'context-menu', 'dialog', 'dropdown-menu', 'hover-card', 'label',
    'menubar', 'navigation-menu', 'popover', 'progress', 'radio-group',
    'scroll-area', 'select', 'separator', 'slider', 'slot', 'switch',
    'tabs', 'toast', 'toggle', 'toggle-group', 'tooltip',
  ];

  it('covers all Shadcn UI Radix primitives', () => {
    for (const component of RADIX_COMPONENTS) {
      const pkg = `@radix-ui/react-${component}`;
      expect(OPTIONAL_DEPENDENCIES, `Missing ${pkg}`).toHaveProperty(pkg);
    }
  });

  it('includes common utility libraries', () => {
    expect(OPTIONAL_DEPENDENCIES).toHaveProperty('axios');
    expect(OPTIONAL_DEPENDENCIES).toHaveProperty('uuid');
    expect(OPTIONAL_DEPENDENCIES).toHaveProperty('nanoid');
  });

  it('has no overlap with PRESET_DEPENDENCIES', () => {
    const presetKeys = new Set(Object.keys(PRESET_DEPENDENCIES));
    for (const key of Object.keys(OPTIONAL_DEPENDENCIES)) {
      expect(presetKeys.has(key), `${key} is in both PRESET and OPTIONAL`).toBe(false);
    }
  });
});

describe('TAILWIND_CSS', () => {
  it('includes Tailwind directives', () => {
    expect(TAILWIND_CSS).toContain('@tailwind base');
    expect(TAILWIND_CSS).toContain('@tailwind components');
    expect(TAILWIND_CSS).toContain('@tailwind utilities');
  });

  it('includes custom animation', () => {
    expect(TAILWIND_CSS).toContain('.animate-in');
    expect(TAILWIND_CSS).toContain('@keyframes fadeIn');
  });

  it('includes scrollbar styling', () => {
    expect(TAILWIND_CSS).toContain('::-webkit-scrollbar');
  });
});

describe('CN_UTILS_CODE', () => {
  it('imports clsx and tailwind-merge', () => {
    expect(CN_UTILS_CODE).toContain("from 'clsx'");
    expect(CN_UTILS_CODE).toContain("from 'tailwind-merge'");
  });

  it('exports cn function', () => {
    expect(CN_UTILS_CODE).toContain('export function cn');
  });

  it('uses twMerge(clsx(...)) pattern', () => {
    expect(CN_UTILS_CODE).toContain('twMerge(clsx(inputs))');
  });
});

describe('TAILWIND_CONFIG', () => {
  it('enables dark mode with class strategy', () => {
    expect(TAILWIND_CONFIG).toContain("darkMode: 'class'");
  });

  it('includes shadcn/ui semantic colors', () => {
    const semanticColors = ['primary', 'secondary', 'destructive', 'muted', 'accent', 'card'];
    for (const color of semanticColors) {
      expect(TAILWIND_CONFIG, `Missing color: ${color}`).toContain(`${color}:`);
    }
  });

  it('includes border and input colors', () => {
    expect(TAILWIND_CONFIG).toContain('border:');
    expect(TAILWIND_CONFIG).toContain('input:');
  });

  it('includes custom border radius', () => {
    expect(TAILWIND_CONFIG).toContain('borderRadius:');
    expect(TAILWIND_CONFIG).toContain('lg:');
    expect(TAILWIND_CONFIG).toContain('md:');
    expect(TAILWIND_CONFIG).toContain('sm:');
  });

  it('scans all relevant file types', () => {
    expect(TAILWIND_CONFIG).toContain('{js,jsx,ts,tsx}');
  });
});
