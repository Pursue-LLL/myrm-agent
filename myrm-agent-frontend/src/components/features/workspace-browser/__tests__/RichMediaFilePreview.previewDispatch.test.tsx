import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useEffect, useState } from 'react';
import { render, screen } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const stableT = (key: string) => key;

vi.mock('@/services/chat', () => ({
  getWorkspaceFileContentUrl: (filePath: string, _workspace: string) => `/api/v1/files/browse/content?path=${encodeURIComponent(filePath)}`,
}));

vi.mock('next/dynamic', () => ({
  __esModule: true,
  default: (loader: () => Promise<unknown>) => {
    const DynamicComponent = (props: Record<string, unknown>) => {
      const [Comp, setComp] = useState<React.ComponentType<Record<string, unknown>> | null>(null);
      useEffect(() => {
        let alive = true;
        loader().then((mod) => {
          if (!alive) return;
          const m = mod as { default?: React.ComponentType<Record<string, unknown>> };
          setComp(() => (m.default ?? mod) as React.ComponentType<Record<string, unknown>>);
        });
        return () => {
          alive = false;
        };
      }, []);
      if (!Comp) return null;
      return <Comp {...props} />;
    };
    return DynamicComponent;
  },
}));

vi.mock('@/components/features/artifacts/renderers/MediaPreview', () => ({
  SvgPreview: ({ content }: { content: string }) => <div data-testid="svg">{content}</div>,
  ImagePreview: () => <div data-testid="image" />,
  VideoPreview: () => <div data-testid="video" />,
  AudioPreview: () => <div data-testid="audio" />,
}));
vi.mock('@/components/features/artifacts/PdfPreview', () => ({ default: () => <div data-testid="pdf" /> }));
vi.mock('@/components/features/artifacts/renderers/DocxPreview', () => ({ default: () => <div data-testid="docx" /> }));
vi.mock('@/components/features/artifacts/renderers/PptxPreview', () => ({ default: () => <div data-testid="pptx" /> }));
vi.mock('@/components/features/artifacts/renderers/SpreadsheetPreview', () => ({ default: () => <div data-testid="xlsx" /> }));

import { getPreviewKind, RichMediaFilePreview } from '../RichMediaFilePreview';

const renderPreview = (filename: string, content?: string) =>
  render(
    <RichMediaFilePreview
      filePath={`/workspace/${filename}`}
      filename={filename}
      workspace="/workspace"
      content={content}
      onDownload={vi.fn()}
    />,
  );

describe('getPreviewKind dispatch', () => {
  it('routes rich media extensions to their renderer kind', () => {
    expect(getPreviewKind('photo.png')).toBe('image');
    expect(getPreviewKind('clip.mov')).toBe('video');
    expect(getPreviewKind('song.flac')).toBe('audio');
    expect(getPreviewKind('report.pdf')).toBe('pdf');
    expect(getPreviewKind('vector.svg')).toBe('svg');
    expect(getPreviewKind('doc.docx')).toBe('docx');
    expect(getPreviewKind('slides.pptx')).toBe('pptx');
    expect(getPreviewKind('data.xlsx')).toBe('xlsx');
    expect(getPreviewKind('legacy.xls')).toBe('xlsx');
  });

  it('matches extensions case-insensitively', () => {
    expect(getPreviewKind('PHOTO.JPG')).toBe('image');
    expect(getPreviewKind('Report.PDF')).toBe('pdf');
    expect(getPreviewKind('Data.XLSX')).toBe('xlsx');
  });

  it('flags known non-previewable binary types as unsupported', () => {
    expect(getPreviewKind('bundle.zip')).toBe('unsupported');
    expect(getPreviewKind('installer.exe')).toBe('unsupported');
    expect(getPreviewKind('font.woff2')).toBe('unsupported');
  });

  it('returns null for text-like files handled by the text editor', () => {
    expect(getPreviewKind('main.py')).toBeNull();
    expect(getPreviewKind('readme.md')).toBeNull();
    expect(getPreviewKind('config.json')).toBeNull();
    expect(getPreviewKind('notes.txt')).toBeNull();
    expect(getPreviewKind('unknown.ext')).toBeNull();
  });
});

describe('RichMediaFilePreview dispatch rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders null for text files', () => {
    const { container } = renderPreview('main.py');
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the image renderer for images', async () => {
    renderPreview('photo.png');
    expect(await screen.findByTestId('image')).toBeTruthy();
  });

  it('renders the pdf renderer for pdfs', async () => {
    renderPreview('report.pdf');
    expect(await screen.findByTestId('pdf')).toBeTruthy();
  });

  it('renders the office renderers for docx/pptx/xlsx', async () => {
    renderPreview('doc.docx');
    expect(await screen.findByTestId('docx')).toBeTruthy();
    renderPreview('slides.pptx');
    expect(await screen.findByTestId('pptx')).toBeTruthy();
    renderPreview('data.xlsx');
    expect(await screen.findByTestId('xlsx')).toBeTruthy();
  });

  it('renders the svg renderer once text content is available', async () => {
    renderPreview('vector.svg', '<svg xmlns="http://www.w3.org/2000/svg"></svg>');
    expect(await screen.findByTestId('svg')).toHaveTextContent('<svg');
  });

  it('renders download fallback for unsupported binary types', async () => {
    renderPreview('bundle.zip');
    expect(await screen.findByText('unsupportedPreview')).toBeTruthy();
    expect(await screen.findByText('download')).toBeTruthy();
  });
});
