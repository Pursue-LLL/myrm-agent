'use client';

/**
 * Rendered view of the text files that have one: markdown as a document, CSV as a table.
 *
 * [INPUT]
 * - kind / content / filePath / filename / workspace: what the file is, its text and where it lives
 * - artifacts/renderers/DocumentPreview and SpreadsheetPreview (POS: the renderers chat artifacts use)
 *
 * [OUTPUT]
 * - getRenderedKind: file name → rendered kind (null = the file only has its source)
 * - RENDER_BY_DEFAULT_MAX_BYTES: size above which a file opens as source
 * - RenderedTextPreview: the rendered view; relative images and links of a markdown file point at the files beside it
 * - ViewSwitch: the Preview / Source choice of the panel header
 *
 * [POS]
 * Lets the workspace panel show what an agent produced the way the chat shows it, while the source stays one click
 * away. Editing always happens on the source.
 */

import React, { memo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { resolveWorkspaceUrl } from './resolveWorkspaceUrl';

export type RenderedKind = 'markdown' | 'csv';
export type TextView = 'rendered' | 'source';

/**
 * Laying out a large document takes seconds on the main thread (a markdown file of 200 KB rendered in about 1.1 s and
 * one of 600 KB in 2.4 s in Chromium), so a larger file opens as source and is rendered when the user asks for it.
 */
export const RENDER_BY_DEFAULT_MAX_BYTES = 200 * 1024;

const RENDERED_EXTENSIONS: Readonly<Record<string, RenderedKind>> = {
  md: 'markdown',
  markdown: 'markdown',
  mdx: 'markdown',
  csv: 'csv',
};

export function getRenderedKind(filename: string): RenderedKind | null {
  const dot = filename.lastIndexOf('.');
  return dot > 0 ? (RENDERED_EXTENSIONS[filename.slice(dot + 1).toLowerCase()] ?? null) : null;
}

const rendererLoading = (
  <div className="h-full w-full flex items-center justify-center">
    <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
  </div>
);

const DocumentPreviewDynamic = dynamic(() => import('../artifacts/renderers/DocumentPreview'), {
  ssr: false,
  loading: () => rendererLoading,
});
const SpreadsheetPreviewDynamic = dynamic(() => import('../artifacts/renderers/SpreadsheetPreview'), {
  ssr: false,
  loading: () => rendererLoading,
});

interface RenderedTextPreviewProps {
  kind: RenderedKind;
  content: string;
  /** Absolute path of the file; relative addresses in a markdown file are resolved against its folder. */
  filePath: string;
  filename: string;
  /** Workspace root boundary for the content API */
  workspace: string;
}

export const RenderedTextPreview: React.FC<RenderedTextPreviewProps> = memo(
  ({ kind, content, filePath, filename, workspace }) => {
    const resolveUrl = useCallback(
      (url: string) => resolveWorkspaceUrl(url, filePath, workspace),
      [filePath, workspace],
    );
    if (kind === 'csv') {
      return <SpreadsheetPreviewDynamic content={content} filename={filename} />;
    }
    return <DocumentPreviewDynamic content={content} filename={filename} resolveUrl={resolveUrl} />;
  },
);
RenderedTextPreview.displayName = 'RenderedTextPreview';

const segment = (active: boolean) =>
  cn(
    'rounded px-2 py-1 transition-colors',
    active ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
  );

export const ViewSwitch: React.FC<{ value: TextView; onChange: (view: TextView) => void }> = memo(
  ({ value, onChange }) => {
    const t = useTranslations('workspace');
    return (
      <div
        // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- a labelled group of toggle buttons; none of the suggested tags fits
        role="group"
        aria-label={t('viewAsLabel')}
        className="mr-1 inline-flex items-center rounded-md border border-border bg-muted/40 p-0.5 text-xs"
      >
        <button
          type="button"
          aria-pressed={value === 'rendered'}
          onClick={() => onChange('rendered')}
          className={segment(value === 'rendered')}
        >
          {t('renderedView')}
        </button>
        <button
          type="button"
          aria-pressed={value === 'source'}
          onClick={() => onChange('source')}
          className={segment(value === 'source')}
        >
          {t('sourceView')}
        </button>
      </div>
    );
  },
);
ViewSwitch.displayName = 'ViewSwitch';
