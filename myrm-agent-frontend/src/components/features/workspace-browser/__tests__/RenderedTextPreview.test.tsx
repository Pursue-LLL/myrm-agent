/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));
vi.mock('next/dynamic', () => ({
  default: () => () => null,
}));
vi.mock('@/services/chat', () => ({
  getWorkspaceFileContentUrl: vi.fn(),
}));
vi.mock('@/lib/api', () => ({
  getStorageUrl: (url: string) => url,
}));

import { getRenderedKind, ViewSwitch } from '../RenderedTextPreview';

describe('getRenderedKind', () => {
  it.each([
    ['README.md', 'markdown'],
    ['notes.MD', 'markdown'],
    ['page.markdown', 'markdown'],
    ['doc.mdx', 'markdown'],
    ['data.csv', 'csv'],
    ['archive.tar.csv', 'csv'],
  ])('knows %s as %s', (name, kind) => {
    expect(getRenderedKind(name)).toBe(kind);
  });

  it.each(['notes.txt', 'config.yaml', 'md', 'csv', '.md', 'Makefile', 'data.csv.bak', ''])(
    'has no rendered view for %s',
    (name) => {
      expect(getRenderedKind(name)).toBeNull();
    },
  );
});

describe('ViewSwitch', () => {
  it('marks the current view, names the group and reports a choice', () => {
    const onChange = vi.fn();
    render(<ViewSwitch value="rendered" onChange={onChange} />);

    expect(screen.getByRole('group', { name: 'viewAsLabel' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'renderedView' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'sourceView' }).getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(screen.getByRole('button', { name: 'sourceView' }));

    expect(onChange).toHaveBeenCalledWith('source');
  });
});
