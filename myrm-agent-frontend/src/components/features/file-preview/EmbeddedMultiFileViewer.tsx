'use client';

/**
 * Six-in-One Embedded Multi-Format File Viewer Component.
 *
 * [INPUT] fileName, fileUrl, content (string or base64/blob), onClose, onDownload
 * [OUTPUT] EmbeddedMultiFileViewer: Pure client viewer supporting Source, Markdown, Image, Audio/Video, PDF, and DOCX.
 * [POS] src/components/features/file-preview/EmbeddedMultiFileViewer.tsx
 */

import { memo, useState, useMemo, useCallback } from 'react';
import {
  FileCode,
  FileText,
  FileImage,
  FileAudio,
  FileVideo,
  FileQuestion,
  Copy,
  Check,
  Download,
  X,
  ExternalLink,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

export type SupportedFileCategory =
  | 'code'
  | 'markdown'
  | 'image'
  | 'media'
  | 'pdf'
  | 'docx'
  | 'unknown';

export interface EmbeddedMultiFileViewerProps {
  fileName: string;
  fileUrl?: string;
  content?: string;
  className?: string;
  onClose?: () => void;
  onDownload?: () => void;
}

export function detectFileCategory(fileName: string): SupportedFileCategory {
  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  if (['ts', 'tsx', 'js', 'jsx', 'json', 'py', 'css', 'html', 'sh', 'yml', 'yaml', 'sql', 'rs', 'go', 'toml'].includes(ext)) {
    return 'code';
  }
  if (['md', 'markdown', 'mdown'].includes(ext)) {
    return 'markdown';
  }
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico'].includes(ext)) {
    return 'image';
  }
  if (['mp3', 'wav', 'ogg', 'mp4', 'webm', 'mov'].includes(ext)) {
    return 'media';
  }
  if (ext === 'pdf') {
    return 'pdf';
  }
  if (['docx', 'doc'].includes(ext)) {
    return 'docx';
  }
  return 'unknown';
}

export const EmbeddedMultiFileViewer = memo(function EmbeddedMultiFileViewer({
  fileName,
  fileUrl,
  content = '',
  className,
  onClose,
  onDownload,
}: EmbeddedMultiFileViewerProps) {
  const t = useTranslations('extensionWidgets');
  const [copied, setCopied] = useState(false);

  const category = useMemo(() => {
    return detectFileCategory(fileName);
  }, [fileName]);

  const handleCopy = useCallback(() => {
    if (!content) {
      return;
    }
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  }, [content]);

  // Extract frontmatter if markdown
  const { frontmatter, markdownBody } = useMemo(() => {
    if (category !== 'markdown' || !content.startsWith('---')) {
      return { frontmatter: null, markdownBody: content };
    }
    const endIdx = content.indexOf('\n---', 3);
    if (endIdx === -1) {
      return { frontmatter: null, markdownBody: content };
    }
    const rawFm = content.slice(3, endIdx).trim();
    const body = content.slice(endIdx + 4).trim();
    const pairs: Record<string, string> = {};
    for (const line of rawFm.split('\n')) {
      const parts = line.split(':');
      if (parts.length >= 2) {
        pairs[parts[0].trim()] = parts.slice(1).join(':').trim();
      }
    }
    return { frontmatter: pairs, markdownBody: body };
  }, [category, content]);

  // Code lines for source viewer
  const codeLines = useMemo(() => {
    return content.split('\n');
  }, [content]);

  const renderIcon = () => {
    switch (category) {
      case 'code':
        return <FileCode className="h-4 w-4 text-sky-500" />;
      case 'markdown':
        return <FileText className="h-4 w-4 text-emerald-500" />;
      case 'image':
        return <FileImage className="h-4 w-4 text-amber-500" />;
      case 'media':
        return fileName.match(/\.(mp4|webm|mov)$/i) ? (
          <FileVideo className="h-4 w-4 text-purple-500" />
        ) : (
          <FileAudio className="h-4 w-4 text-pink-500" />
        );
      case 'pdf':
        return <FileText className="h-4 w-4 text-rose-500" />;
      case 'docx':
        return <FileText className="h-4 w-4 text-blue-500" />;
      default:
        return <FileQuestion className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <div
      className={cn(
        'flex flex-col h-full w-full rounded-xl border border-border bg-background shadow-xl overflow-hidden text-foreground',
        className,
      )}
      data-testid="embedded-multi-file-viewer"
    >
      {/* Header bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-border/60 bg-muted/30 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          {renderIcon()}
          <span className="font-semibold text-xs truncate max-w-[240px] sm:max-w-md">
            {fileName}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono uppercase text-muted-foreground">
            {category}
          </span>
        </div>

        <div className="flex items-center gap-1">
          {content && (
            <button
              type="button"
              onClick={handleCopy}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title={t('copyContent') || 'Copy Content'}
              aria-label="Copy"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          )}

          {fileUrl && (
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title={t('openExternal') || 'Open in new tab'}
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}

          {onDownload && (
            <button
              type="button"
              onClick={onDownload}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title={t('download') || 'Download'}
            >
              <Download className="h-3.5 w-3.5" />
            </button>
          )}

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors ml-1"
              title={t('close') || 'Close'}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Main Preview Container */}
      <div className="flex-1 overflow-auto p-4 bg-muted/10 relative">
        {/* 1. Source Code Viewer */}
        {category === 'code' && (
          <div className="flex font-mono text-xs leading-relaxed select-text">
            <div className="pr-3 text-right text-muted-foreground/50 select-none border-r border-border/40 mr-3">
              {codeLines.map((_, i) => (
                <div key={`ln-${i + 1}`}>{i + 1}</div>
              ))}
            </div>
            <pre className="flex-1 whitespace-pre-wrap break-words m-0 overflow-x-auto text-foreground">
              {content || '// Empty file'}
            </pre>
          </div>
        )}

        {/* 2. Markdown Viewer with Frontmatter */}
        {category === 'markdown' && (
          <div className="max-w-3xl mx-auto flex flex-col gap-3">
            {frontmatter && Object.keys(frontmatter).length > 0 && (
              <div className="p-3 rounded-lg border border-border/80 bg-muted/40 text-xs">
                <span className="font-semibold text-muted-foreground block mb-1 uppercase text-[10px] tracking-wider">
                  Frontmatter Metadata
                </span>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px]">
                  {Object.entries(frontmatter).map(([k, v]) => (
                    <div key={k} className="flex gap-1.5">
                      <span className="text-muted-foreground">{k}:</span>
                      <span className="text-foreground font-medium truncate">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="prose dark:prose-invert max-w-none text-xs leading-relaxed whitespace-pre-wrap">
              {markdownBody || 'Empty markdown document'}
            </div>
          </div>
        )}

        {/* 3. Image Viewer */}
        {category === 'image' && (
          <div className="flex items-center justify-center h-full min-h-[240px]">
            {fileUrl ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={fileUrl}
                alt={fileName}
                className="max-h-full max-w-full rounded-lg object-contain shadow-md"
              />
            ) : (
              <div className="text-xs text-muted-foreground">{t('noImageSource') || 'No image source provided'}</div>
            )}
          </div>
        )}

        {/* 4. Audio / Video Media Player */}
        {category === 'media' && (
          <div className="flex items-center justify-center h-full min-h-[200px]">
            {fileName.match(/\.(mp4|webm|mov)$/i) ? (
              <video controls className="max-h-96 max-w-full rounded-lg shadow-md" src={fileUrl}>
                <track kind="captions" />
              </video>
            ) : (
              <audio controls className="w-full max-w-md" src={fileUrl}>
                <track kind="captions" />
              </audio>
            )}
          </div>
        )}

        {/* 5. PDF Native Embedded Viewer */}
        {category === 'pdf' && (
          <div className="w-full h-full min-h-[400px]">
            {fileUrl ? (
              <object
                data={fileUrl}
                type="application/pdf"
                className="w-full h-full min-h-[450px] rounded border border-border"
              >
                <div className="p-4 text-xs text-center text-muted-foreground">
                  <p>{t('pdfFallback') || 'PDF plugin not supported in this container.'}</p>
                  <a href={fileUrl} className="underline text-primary mt-1 inline-block" target="_blank" rel="noreferrer">
                    {t('downloadPdf') || 'Download PDF to view'}
                  </a>
                </div>
              </object>
            ) : (
              <div className="text-xs text-muted-foreground text-center py-12">{t('noPdfSource') || 'No PDF source URL available'}</div>
            )}
          </div>
        )}

        {/* 6. DOCX Structured Text Viewer */}
        {category === 'docx' && (
          <div className="max-w-2xl mx-auto p-4 bg-background rounded-lg border border-border/80 shadow-sm text-xs leading-relaxed">
            <div className="border-b border-border/40 pb-2 mb-3 font-semibold text-muted-foreground uppercase text-[10px]">
              Word Document Preview
            </div>
            <div className="whitespace-pre-wrap font-sans text-foreground">
              {content || 'Document contents processed without native MS Word installation.'}
            </div>
          </div>
        )}

        {/* Unknown fallback */}
        {category === 'unknown' && (
          <div className="flex flex-col items-center justify-center h-full py-12 text-center text-xs text-muted-foreground">
            <FileQuestion className="h-8 w-8 mb-2 opacity-50" />
            <p>{t('unsupportedFormat') || 'Preview not available for this file type'}</p>
            {content && <pre className="mt-4 p-2 bg-muted rounded max-w-lg text-left overflow-auto">{content.slice(0, 500)}</pre>}
          </div>
        )}
      </div>
    </div>
  );
});
