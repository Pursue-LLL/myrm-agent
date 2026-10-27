/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DocumentPreview from '../DocumentPreview';

const toolbarContent = vi.hoisted(() => ({ seen: [] as string[] }));

vi.mock('@/components/features/markdown-render-tools/MermaidChart', () => ({
  default: () => <div data-testid="mermaid" />,
}));
vi.mock('@/components/features/markdown-render-tools/CodeBlock', () => ({
  default: ({ value }: { value: string }) => <pre data-testid="code-block">{value}</pre>,
}));
vi.mock('@/components/features/artifacts/portal/DocumentSelectionToolbar', () => ({
  default: ({ content }: { content: string }) => {
    toolbarContent.seen.push(content);
    return <div data-testid="selection-toolbar" />;
  },
}));

const WITH_META = '---\nname: weekly-report\ntags: [weekly, ops]\n---\n# Weekly report\n\nBody text.';

describe('DocumentPreview markdown', () => {
  it('does not render the front matter block as a rule, a heading and text', async () => {
    const { container } = render(<DocumentPreview content={WITH_META} filename="report.md" />);

    await screen.findByRole('heading', { name: 'Weekly report' });
    expect(container.querySelectorAll('hr')).toHaveLength(0);
    expect(container.textContent).not.toContain('name: weekly-report');
    expect(container.textContent).toContain('Body text.');
  });

  it('keeps a document that opens with a rule and has another one further down whole', async () => {
    const { container } = render(<DocumentPreview content={'---\n# Title\nSome text\n---\nmore'} filename="a.md" />);

    await screen.findByRole('heading', { name: 'Title' });
    expect(container.textContent).toContain('Some text');
    expect(container.textContent).toContain('more');
  });

  it('hands the selection toolbar the whole file, so a selection is found at its place in the file', async () => {
    toolbarContent.seen.length = 0;
    render(<DocumentPreview content={WITH_META} filename="report.md" artifactId="art-1" />);

    await screen.findByTestId('selection-toolbar');
    expect(toolbarContent.seen.every((content) => content === WITH_META)).toBe(true);
  });

  it('shows plain text documents exactly as they are, front matter included', () => {
    const { container } = render(<DocumentPreview content={WITH_META} filename="report.txt" />);
    expect(container.querySelector('pre')?.textContent).toBe(WITH_META);
  });
});

describe('DocumentPreview resolveUrl', () => {
  const resolveUrl = (url: string) => `/files?path=${encodeURIComponent(url)}`;

  it('lets the host decide where relative images and links point', async () => {
    const content = '![logo](img/logo.png)\n\n[notes](notes.md)\n\n[site](https://example.com)';
    render(<DocumentPreview content={content} filename="README.md" resolveUrl={resolveUrl} />);

    const image = await screen.findByRole('img', { name: 'logo' });
    await waitFor(() => expect(image.getAttribute('src')).toBe('/files?path=img%2Flogo.png'));
    expect(screen.getByRole('link', { name: 'notes' }).getAttribute('href')).toBe('/files?path=notes.md');
    expect(screen.getByRole('link', { name: 'site' }).getAttribute('href')).toBe(
      '/files?path=' + encodeURIComponent('https://example.com'),
    );
  });

  it('leaves addresses alone when no host resolver is given', async () => {
    render(<DocumentPreview content="![logo](img/logo.png)" filename="README.md" />);

    const image = await screen.findByRole('img', { name: 'logo' });
    expect(image.getAttribute('src')).toBe('img/logo.png');
  });
});
