'use client';

import React, { useState, useRef, memo } from 'react';
import { useTranslations } from 'next-intl';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { IconPdf } from '@/components/ui/icons/PremiumIcons';

// 配置 PDF.js worker（使用 CDN）
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PdfPreviewProps {
  url: string;
  filename: string;
}

/** PDF 预览组件 */
const PdfPreview: React.FC<PdfPreviewProps> = memo(({ url, filename }) => {
  const t = useTranslations('artifacts');
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1.0);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setIsLoading(false);
  };

  const onDocumentLoadError = () => {
    setHasError(true);
    setIsLoading(false);
  };

  const goToPrevPage = () => setPageNumber((prev) => Math.max(prev - 1, 1));
  const goToNextPage = () => setPageNumber((prev) => Math.min(prev + 1, numPages || prev));
  const zoomIn = () => setScale((prev) => Math.min(prev + 0.25, 3));
  const zoomOut = () => setScale((prev) => Math.max(prev - 0.25, 0.5));

  // 计算适合容器的宽度
  const containerWidth = containerRef.current?.clientWidth || 600;
  const pageWidth = Math.min(containerWidth - 48, 800) * scale;

  if (hasError) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center gap-4 text-muted-foreground">
        <div className="w-20 h-20 rounded-2xl bg-muted flex items-center justify-center">
          <IconPdf className="w-10 h-10 text-muted-foreground" />
        </div>
        <div className="text-center">
          <p className="font-medium">{t('pdfLoadError')}</p>
          <p className="text-sm mt-1">{filename}</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full w-full flex flex-col bg-muted/30">
      {/* 工具栏 */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-border bg-background/80 backdrop-blur-sm">
        {/* 页码导航 */}
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={goToPrevPage} disabled={pageNumber <= 1} className="h-8 w-8 p-0">
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-muted-foreground min-w-[80px] text-center">
            {pageNumber} / {numPages || '...'}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={goToNextPage}
            disabled={pageNumber >= (numPages || 1)}
            className="h-8 w-8 p-0"
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>

        {/* 缩放控制 */}
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={zoomOut} disabled={scale <= 0.5} className="h-8 w-8 p-0">
            <ZoomOut className="w-4 h-4" />
          </Button>
          <span className="text-sm text-muted-foreground min-w-[50px] text-center">{Math.round(scale * 100)}%</span>
          <Button variant="ghost" size="sm" onClick={zoomIn} disabled={scale >= 3} className="h-8 w-8 p-0">
            <ZoomIn className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* PDF 内容区域 */}
      <div className="flex-1 overflow-auto flex justify-center p-4">
        {isLoading && (
          <div className="flex items-center justify-center">
            <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
          </div>
        )}
        <Document
          file={url}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={null}
          className="flex justify-center"
        >
          <Page
            pageNumber={pageNumber}
            width={pageWidth}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            className="shadow-lg rounded-lg overflow-hidden"
          />
        </Document>
      </div>
    </div>
  );
});

PdfPreview.displayName = 'PdfPreview';

export default PdfPreview;
