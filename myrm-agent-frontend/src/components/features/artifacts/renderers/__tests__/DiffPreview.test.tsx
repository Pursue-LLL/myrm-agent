import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import React from 'react';
import type { ArtifactVersion } from '@/store/chat/types';

vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'dark' }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const t = (key: string) => {
      const map: Record<string, string> = {
        'diff.inline': 'Inline',
        'diff.sideBySide': 'Side by Side',
        'diff.noVersions': 'At least two versions are required',
      };
      return map[key] ?? key;
    };
    return t;
  },
}));

vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({
  LazyMonacoDiffEditor: ({
    original,
    modified,
    language,
    options,
  }: {
    original: string;
    modified: string;
    language: string;
    options: { renderSideBySide: boolean };
  }) => (
    <div
      data-testid="monaco-diff-editor"
      data-original={original}
      data-modified={modified}
      data-language={language}
      data-side-by-side={String(options.renderSideBySide)}
    />
  ),
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/lib/constants/artifact', () => ({
  MOBILE_BREAKPOINT: 768,
}));

import DiffPreview from '../DiffPreview';

function makeVersions(contents: string[]): ArtifactVersion[] {
  return contents.map((content, i) => ({
    versionId: `v${i + 1}`,
    versionNumber: i + 1,
    content,
    createdAt: new Date(2026, 0, i + 1).toISOString(),
  }));
}

describe('DiffPreview', () => {
  it('renders fallback when less than 2 versions', () => {
    const versions = makeVersions(['hello']);
    render(
      <DiffPreview
        currentContent="hello"
        versions={versions}
        viewingVersionIndex={-1}
        language="plaintext"
      />,
    );
    expect(screen.getByText('At least two versions are required')).toBeInTheDocument();
  });

  it('renders Monaco DiffEditor with correct original/modified when viewing latest', () => {
    const versions = makeVersions(['version 1 content', 'version 2 content']);
    render(
      <DiffPreview
        currentContent="version 2 content"
        versions={versions}
        viewingVersionIndex={-1}
        language="python"
      />,
    );
    const editor = screen.getByTestId('monaco-diff-editor');
    expect(editor).toBeInTheDocument();
    expect(editor.getAttribute('data-original')).toBe('version 1 content');
    expect(editor.getAttribute('data-modified')).toBe('version 2 content');
    expect(editor.getAttribute('data-language')).toBe('python');
    expect(editor.getAttribute('data-side-by-side')).toBe('true');
  });

  it('renders correct diff when viewing a specific version', () => {
    const versions = makeVersions(['v1', 'v2', 'v3']);
    render(
      <DiffPreview
        currentContent="v3"
        versions={versions}
        viewingVersionIndex={1}
        language="javascript"
      />,
    );
    const editor = screen.getByTestId('monaco-diff-editor');
    expect(editor.getAttribute('data-original')).toBe('v1');
    expect(editor.getAttribute('data-modified')).toBe('v2');
  });

  it('switches between inline and side-by-side mode', () => {
    const versions = makeVersions(['old', 'new']);
    render(
      <DiffPreview
        currentContent="new"
        versions={versions}
        viewingVersionIndex={-1}
        language="plaintext"
      />,
    );

    const editor = screen.getByTestId('monaco-diff-editor');
    expect(editor.getAttribute('data-side-by-side')).toBe('true');

    fireEvent.click(screen.getByText('Inline'));
    expect(screen.getByTestId('monaco-diff-editor').getAttribute('data-side-by-side')).toBe('false');

    fireEvent.click(screen.getByText('Side by Side'));
    expect(screen.getByTestId('monaco-diff-editor').getAttribute('data-side-by-side')).toBe('true');
  });

  it('displays version labels in toolbar', () => {
    const versions = makeVersions(['v1', 'v2', 'v3']);
    render(
      <DiffPreview
        currentContent="v3"
        versions={versions}
        viewingVersionIndex={-1}
        language="plaintext"
      />,
    );
    expect(screen.getByText('V2 → V3')).toBeInTheDocument();
  });

  it('uses empty string for original when viewing version index 0', () => {
    const versions = makeVersions(['first', 'second']);
    render(
      <DiffPreview
        currentContent="second"
        versions={versions}
        viewingVersionIndex={0}
        language="plaintext"
      />,
    );
    const editor = screen.getByTestId('monaco-diff-editor');
    expect(editor.getAttribute('data-original')).toBe('');
    expect(editor.getAttribute('data-modified')).toBe('first');
  });
});
