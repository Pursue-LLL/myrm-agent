'use client';

/**
 * [INPUT]
 * docx-preview::renderAsync (POS: DOCX 二进制解析与 HTML 渲染);
 * @/lib/api::getStorageUrl (POS: 存储 URL 构建).
 * [OUTPUT] DocxPreview: Word 文档高保真预览渲染器。
 * [POS] 通过 docx-preview 库将 .docx 二进制文件解析并渲染为带样式的 HTML DOM。
 */

import React, { memo, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { getStorageUrl } from '@/lib/api';

interface DocxPreviewProps {
  previewUrl: string;
}

const DocxPreview: React.FC<DocxPreviewProps> = memo(({ previewUrl }) => {
  const t = useTranslations('artifacts');
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;

    const render = async () => {
      setLoading(true);
      setError(null);

      try {
        const res = await fetch(getStorageUrl(previewUrl));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();

        if (cancelled) return;

        const { renderAsync } = await import('docx-preview');
        container.innerHTML = '';

        await renderAsync(blob, container, container, {
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          breakPages: true,
          ignoreLastRenderedPageBreak: true,
          experimental: false,
          trimXmlDeclaration: true,
          useBase64URL: true,
        });
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    render();
    return () => {
      cancelled = true;
      if (container) container.innerHTML = '';
    };
  }, [previewUrl]);

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 p-4">
        <p className="text-sm text-destructive">{t('docxLoadError')}</p>
        <p className="text-xs text-muted-foreground">{error}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-muted/30">
      {loading && (
        <div className="h-full flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
        </div>
      )}
      <div
        ref={containerRef}
        className="docx-preview-container mx-auto"
        style={{ display: loading ? 'none' : 'block' }}
      />
    </div>
  );
});

DocxPreview.displayName = 'DocxPreview';
export default DocxPreview;
