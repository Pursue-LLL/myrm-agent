'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import { Artifact } from '@/store/chat/types';
import { ArtifactDisplayMode } from '@/store/useArtifactPortalStore';
import { isSvgType, isMermaidType } from './artifactUtils';
import ArtifactErrorBoundary from './ArtifactErrorBoundary';
import { getStorageUrl } from '@/lib/api';

// 渲染器组件
import CodePreview from './renderers/CodePreview';
import DocumentPreview from './renderers/DocumentPreview';
import MermaidPreview from './renderers/MermaidPreview';
import SkeletonLoader from './renderers/SkeletonLoader';
import NoPreview from './renderers/NoPreview';
import { HtmlPreview, ImagePreview, VideoPreview, SvgPreview, AudioPreview } from './renderers/MediaPreview';

// 动态导入 PDF 预览组件
const PdfPreviewDynamic = dynamic(() => import('./PdfPreview'), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center">
      <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
    </div>
  ),
});

// 动态导入表格预览组件
const SpreadsheetPreviewDynamic = dynamic(() => import('./renderers/SpreadsheetPreview'), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center">
      <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
    </div>
  ),
});

// 动态导入 React 预览组件
const ReactPreviewDynamic = dynamic(() => import('./ReactPreview'), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center bg-muted/30">
      <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
    </div>
  ),
});

interface ArtifactRendererProps {
  artifact: Artifact;
  content: string;
  displayMode: ArtifactDisplayMode;
  loading: boolean;
  onDownload: () => void;
}

/** 内部渲染器 */
const InnerRenderer: React.FC<ArtifactRendererProps> = ({ artifact, content, displayMode, loading, onDownload }) => {
  const t = useTranslations('artifacts');

  if (loading) {
    return <SkeletonLoader type={artifact.type} />;
  }

  const { type, preview_url, filename, content_type } = artifact;
  const cannotPreview = ['binary'].includes(type);

  // 检查特殊类型
  const isSvg = type === 'svg' || isSvgType(content_type, filename);
  const isMermaid = type === 'mermaid' || isMermaidType(content_type, filename);
  const isPdf = type === 'pdf' || content_type === 'application/pdf' || filename.toLowerCase().endsWith('.pdf');
  const isSpreadsheet =
    type === 'spreadsheet' ||
    /\.(csv|tsv|xlsx|xls)$/i.test(filename) ||
    content_type === 'text/csv' ||
    content_type === 'text/tab-separated-values' ||
    content_type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    content_type === 'application/vnd.ms-excel';

  // 检测是否为 React/JSX/TSX 文件
  const isReactFile =
    /\.(jsx|tsx)$/i.test(filename) ||
    (filename.endsWith('.js') &&
      content &&
      (content.includes('import React') ||
        content.includes('from "react"') ||
        content.includes("from 'react'") ||
        /<[A-Z][a-zA-Z0-9]*/.test(content)));

  // 检测深色模式
  const isDarkMode = typeof window !== 'undefined' && document.documentElement.classList.contains('dark');

  // 无法预览的类型
  if (cannotPreview) {
    return <NoPreview artifact={artifact} onDownload={onDownload} />;
  }

  // PDF 预览
  if (isPdf) {
    return <PdfPreviewDynamic url={getStorageUrl(preview_url)} filename={filename} />;
  }

  // 表格/电子表格预览
  if (isSpreadsheet) {
    if (displayMode === ArtifactDisplayMode.Code && content) {
      return <CodePreview content={content} language="csv" artifactId={artifact.id} />;
    }
    return (
      <SpreadsheetPreviewDynamic
        content={content || ''}
        filename={filename}
        previewUrl={preview_url || undefined}
      />
    );
  }

  // React/JSX/TSX 组件预览
  if (isReactFile && content && displayMode === ArtifactDisplayMode.Preview) {
    return <ReactPreviewDynamic code={content} filename={filename} isDarkMode={isDarkMode} />;
  }

  // SVG 内联渲染
  if (isSvg && content) {
    return displayMode === ArtifactDisplayMode.Code ? (
      <CodePreview content={content} language="xml" artifactId={artifact.id} />
    ) : (
      <SvgPreview content={content} />
    );
  }

  // Mermaid 图表渲染
  if (isMermaid && content) {
    return displayMode === ArtifactDisplayMode.Code ? (
      <CodePreview content={content} language="mermaid" artifactId={artifact.id} />
    ) : (
      <MermaidPreview content={content} />
    );
  }

  // 代码/文档类型
  if (['code', 'document'].includes(type)) {
    if (displayMode === ArtifactDisplayMode.Code) {
      return <CodePreview content={content} language={artifact.language} artifactId={artifact.id} />;
    }
    if (isReactFile) {
      return <CodePreview content={content} language={artifact.language || 'jsx'} artifactId={artifact.id} />;
    }
    return type === 'code' ? (
      <CodePreview content={content} language={artifact.language} artifactId={artifact.id} />
    ) : (
      <DocumentPreview content={content} filename={filename} />
    );
  }

  // HTML 类型 - 支持预览和源码切换
  if (type === 'html') {
    if (displayMode === ArtifactDisplayMode.Code) {
      return <CodePreview content={content} language="html" artifactId={artifact.id} />;
    }
    // 优先使用远程 URL，如果没有则使用内容创建 Blob URL
    const htmlUrl = preview_url ? getStorageUrl(preview_url) : undefined;
    return <HtmlPreview url={htmlUrl} content={content} />;
  }

  // 视频类型
  if (type === 'video') {
    return <VideoPreview url={getStorageUrl(preview_url)} filename={filename} errorMessage={t('videoLoadError')} />;
  }

  // 图片类型
  if (type === 'image') {
    return <ImagePreview url={getStorageUrl(preview_url)} filename={filename} errorMessage={t('imageLoadError')} />;
  }

  // 音频类型
  if (type === 'audio') {
    return <AudioPreview url={getStorageUrl(preview_url)} filename={filename} errorMessage={t('audioLoadError')} />;
  }

  // 默认：无法预览
  return <NoPreview artifact={artifact} onDownload={onDownload} />;
};

/** Artifact 渲染器主组件（带错误边界） */
const ArtifactRenderer: React.FC<ArtifactRendererProps> = (props) => {
  const t = useTranslations('artifacts');

  return (
    <ArtifactErrorBoundary fallbackMessage={t('errors.parseError')}>
      <InnerRenderer {...props} />
    </ArtifactErrorBoundary>
  );
};

export default memo(ArtifactRenderer);
