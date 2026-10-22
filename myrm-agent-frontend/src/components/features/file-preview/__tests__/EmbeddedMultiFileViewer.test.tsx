/**
 * Unit tests for EmbeddedMultiFileViewer component.
 *
 * [INPUT] EmbeddedMultiFileViewer, detectFileCategory
 * [OUTPUT] Full coverage tests for multi-format previewing, frontmatter parsing, and user interactions.
 * [POS] src/components/features/file-preview/__tests__/EmbeddedMultiFileViewer.test.tsx
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EmbeddedMultiFileViewer, detectFileCategory } from '../EmbeddedMultiFileViewer';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    copyContent: 'Copy Content',
    openExternal: 'Open in new tab',
    download: 'Download',
    close: 'Close',
    unsupportedFormat: 'Preview not available for this file type',
    pdfFallback: 'PDF plugin not supported in this container.',
    downloadPdf: 'Download PDF to view',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('detectFileCategory', () => {
  it('correctly maps file extensions to preview categories', () => {
    expect(detectFileCategory('index.ts')).toBe('code');
    expect(detectFileCategory('script.py')).toBe('code');
    expect(detectFileCategory('README.md')).toBe('markdown');
    expect(detectFileCategory('photo.png')).toBe('image');
    expect(detectFileCategory('song.mp3')).toBe('media');
    expect(detectFileCategory('video.mp4')).toBe('media');
    expect(detectFileCategory('doc.pdf')).toBe('pdf');
    expect(detectFileCategory('notes.docx')).toBe('docx');
    expect(detectFileCategory('unknown.xyz123')).toBe('unknown');
  });
});

describe('EmbeddedMultiFileViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders code file with line numbers and copy button', async () => {
    const mockWriteText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: mockWriteText,
      },
    });

    const code = 'const a = 1;\nconst b = 2;\nconsole.log(a + b);';
    render(<EmbeddedMultiFileViewer fileName="app.ts" content={code} />);

    expect(screen.getByText('app.ts')).toBeInTheDocument();
    expect(screen.getByText('code')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();

    const copyBtn = screen.getByRole('button', { name: 'Copy' });
    fireEvent.click(copyBtn);
    expect(mockWriteText).toHaveBeenCalledWith(code);
  });

  it('renders markdown file and extracts frontmatter correctly', () => {
    const mdContent = `---
title: System Architecture
version: 2.0
---
# Main Content
This is the body text.`;

    render(<EmbeddedMultiFileViewer fileName="arch.md" content={mdContent} />);

    expect(screen.getByText('System Architecture')).toBeInTheDocument();
    expect(screen.getByText('version:')).toBeInTheDocument();
    expect(screen.getByText('2.0')).toBeInTheDocument();
    expect(screen.getByText(/# Main Content/)).toBeInTheDocument();
  });

  it('renders image when category is image and fileUrl is provided', () => {
    render(<EmbeddedMultiFileViewer fileName="diagram.png" fileUrl="https://example.com/diagram.png" />);

    const img = screen.getByRole('img');
    expect(img).toHaveAttribute('src', 'https://example.com/diagram.png');
    expect(img).toHaveAttribute('alt', 'diagram.png');
  });

  it('renders video and audio player for media category', () => {
    const { unmount } = render(<EmbeddedMultiFileViewer fileName="demo.mp4" fileUrl="https://example.com/demo.mp4" />);
    expect(document.querySelector('video')).toHaveAttribute('src', 'https://example.com/demo.mp4');
    unmount();

    render(<EmbeddedMultiFileViewer fileName="podcast.mp3" fileUrl="https://example.com/podcast.mp3" />);
    expect(document.querySelector('audio')).toHaveAttribute('src', 'https://example.com/podcast.mp3');
  });

  it('renders native object for PDF and structured view for DOCX', () => {
    const { unmount } = render(
      <EmbeddedMultiFileViewer fileName="whitepaper.pdf" fileUrl="https://example.com/whitepaper.pdf" />,
    );
    expect(document.querySelector('object')).toHaveAttribute('data', 'https://example.com/whitepaper.pdf');
    unmount();

    render(<EmbeddedMultiFileViewer fileName="report.docx" content="Converted DOCX text content" />);
    expect(screen.getByText('Word Document Preview')).toBeInTheDocument();
    expect(screen.getByText('Converted DOCX text content')).toBeInTheDocument();
  });

  it('triggers onDownload and onClose callbacks when corresponding buttons are clicked', () => {
    const onDownload = vi.fn();
    const onClose = vi.fn();

    render(
      <EmbeddedMultiFileViewer
        fileName="test.txt"
        fileUrl="https://example.com/test.txt"
        content="Hello"
        onDownload={onDownload}
        onClose={onClose}
      />,
    );

    const downloadBtn = screen.getByTitle('Download');
    fireEvent.click(downloadBtn);
    expect(onDownload).toHaveBeenCalledTimes(1);

    const closeBtn = screen.getByTitle('Close');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
