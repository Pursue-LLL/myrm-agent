'use client';

/**
 * [INPUT]
 * - @/services/chat::getWorkspaceFileContentUrl (POS: workspace file content URL builder)
 * - artifacts/renderers/MediaPreview::ImagePreview/VideoPreview/AudioPreview/SvgPreview
 *   (POS: artifact rich media renderers)
 * - artifacts/PdfPreview (POS: react-pdf viewer) · artifacts/renderers/DocxPreview
 *   (POS: docx-preview renderer) · artifacts/renderers/PptxPreview (POS: pptx-renderer)
 *   · artifacts/renderers/SpreadsheetPreview (POS: xlsx/csv data grid)
 *
 * [OUTPUT]
 * - getPreviewKind: filename → rich preview kind (null = treat as text)
 * - RichMediaFilePreview: workspace rich-media file preview dispatcher
 *
 * [POS]
 * Workspace file browser rich-media preview layer. Routes binary files
 * (images/audio/video/PDF/office docs) to the existing artifact renderers so
 * they render natively instead of as garbled text.
 */

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import { Download, FileQuestion } from 'lucide-react';
import { getWorkspaceFileContentUrl } from '@/services/chat';
import { getStorageUrl } from '@/lib/api';
import { SvgPreview } from '@/components/features/artifacts/renderers/MediaPreview';

export type PreviewKind = 'image' | 'video' | 'audio' | 'pdf' | 'svg' | 'docx' | 'pptx' | 'xlsx' | 'unsupported';

const RICH_EXT: Record<string, PreviewKind> = {
  png: 'image',
  jpg: 'image',
  jpeg: 'image',
  gif: 'image',
  webp: 'image',
  avif: 'image',
  bmp: 'image',
  ico: 'image',
  mp4: 'video',
  webm: 'video',
  mov: 'video',
  m4v: 'video',
  mp3: 'audio',
  wav: 'audio',
  aac: 'audio',
  flac: 'audio',
  m4a: 'audio',
  opus: 'audio',
  pdf: 'pdf',
  svg: 'svg',
  docx: 'docx',
  pptx: 'pptx',
  xlsx: 'xlsx',
  xls: 'xlsx',
};

const UNSUPPORTED_EXT: ReadonlySet<string> = new Set([
  'zip',
  '7z',
  'rar',
  'tar',
  'gz',
  'bz2',
  'xz',
  'iso',
  'dmg',
  'exe',
  'msi',
  'bin',
  'apk',
  'ipa',
  'class',
  'o',
  'a',
  'so',
  'dylib',
  'pyc',
  'woff',
  'woff2',
  'ttf',
  'otf',
  'eot',
]);

export function getPreviewKind(filename: string): PreviewKind | null {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (RICH_EXT[ext]) return RICH_EXT[ext];
  if (UNSUPPORTED_EXT.has(ext)) return 'unsupported';
  return null;
}

const rendererLoading = (
  <div className="h-full w-full flex items-center justify-center">
    <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
  </div>
);

const ImagePreviewDynamic = dynamic(() => import('../artifacts/renderers/MediaPreview').then((m) => m.ImagePreview), {
  ssr: false,
  loading: () => rendererLoading,
});
const VideoPreviewDynamic = dynamic(() => import('../artifacts/renderers/MediaPreview').then((m) => m.VideoPreview), {
  ssr: false,
  loading: () => rendererLoading,
});
const AudioPreviewDynamic = dynamic(() => import('../artifacts/renderers/MediaPreview').then((m) => m.AudioPreview), {
  ssr: false,
  loading: () => rendererLoading,
});
const PdfPreviewDynamic = dynamic(() => import('../artifacts/PdfPreview'), {
  ssr: false,
  loading: () => rendererLoading,
});
const DocxPreviewDynamic = dynamic(() => import('../artifacts/renderers/DocxPreview'), {
  ssr: false,
  loading: () => rendererLoading,
});
const PptxPreviewDynamic = dynamic(() => import('../artifacts/renderers/PptxPreview'), {
  ssr: false,
  loading: () => rendererLoading,
});
const SpreadsheetPreviewDynamic = dynamic(() => import('../artifacts/renderers/SpreadsheetPreview'), {
  ssr: false,
  loading: () => rendererLoading,
});

interface RichMediaFilePreviewProps {
  /** Absolute workspace file path */
  filePath: string;
  /** File name (used for kind detection and renderer labels) */
  filename: string;
  /** Workspace root boundary for the content API */
  workspace: string;
  /** Inline SVG text content (fetched by the caller) */
  content?: string;
  /** Trigger download fallback for unsupported types */
  onDownload: () => void;
  /** Override kind derived from the filename (e.g. backend is_text=false for unknown binary) */
  kind?: PreviewKind;
}

/** Preview dispatcher for workspace binary files. Renders null for text kinds. */
export const RichMediaFilePreview: React.FC<RichMediaFilePreviewProps> = memo(
  ({ filePath, filename, workspace, content, onDownload, kind: kindOverride }) => {
    const t = useTranslations('workspace');
    const kind = kindOverride ?? getPreviewKind(filename);
    if (!kind) return null;

    const previewUrl = getStorageUrl(getWorkspaceFileContentUrl(filePath, workspace));

    switch (kind) {
      case 'image':
        return (
          <ImagePreviewDynamic
            url={previewUrl}
            filename={filename}
            errorMessage={t('previewLoadError')}
            showEditButton={false}
          />
        );
      case 'video':
        return <VideoPreviewDynamic url={previewUrl} filename={filename} errorMessage={t('previewLoadError')} />;
      case 'audio':
        return <AudioPreviewDynamic url={previewUrl} filename={filename} errorMessage={t('previewLoadError')} />;
      case 'pdf':
        return <PdfPreviewDynamic url={previewUrl} filename={filename} />;
      case 'svg':
        return content ? <SvgPreview content={content} /> : null;
      case 'docx':
        return <DocxPreviewDynamic previewUrl={previewUrl} />;
      case 'pptx':
        return <PptxPreviewDynamic previewUrl={previewUrl} />;
      case 'xlsx':
        return <SpreadsheetPreviewDynamic content="" filename={filename} previewUrl={previewUrl} />;
      case 'unsupported':
        return (
          <div
            data-testid="workspace-preview-unsupported"
            className="flex flex-col items-center justify-center h-full gap-3 px-4 text-muted-foreground"
          >
            <FileQuestion className="h-8 w-8 mb-1" />
            <span className="text-sm text-center">{t('unsupportedPreview')}</span>
            <button
              onClick={onDownload}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-muted transition-colors text-foreground"
            >
              <Download className="h-3.5 w-3.5" />
              {t('download')}
            </button>
          </div>
        );
    }
  },
);

RichMediaFilePreview.displayName = 'RichMediaFilePreview';
