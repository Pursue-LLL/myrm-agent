'use client';

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Artifact, ArtifactType } from '@/store/chat/types';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import {
  Download,
  Copy,
  Check,
  ExternalLink,
  FileCode,
  FileText,
  Globe,
  Image,
  Video,
  File,
  FileSpreadsheet,
} from 'lucide-react';
import dynamic from 'next/dynamic';
import { getStorageUrl } from '@/lib/api';
import { getDownloadFilename } from './artifactUtils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

import { DeployModal } from './DeployModal';

// 动态导入 PDF 预览组件（包含 react-pdf 配置）
const PdfPreviewDynamic = dynamic(() => import('./PdfPreview'), {
  ssr: false,
  loading: () => (
    <div className="h-full flex items-center justify-center">
      <div className="animate-spin w-8 h-8 border-2 border-gray-300 dark:border-gray-600 border-t-primary rounded-full" />
    </div>
  ),
});

interface ArtifactPreviewProps {
  artifact: Artifact | null;
  open: boolean;
  onClose: () => void;
}

// 格式化文件大小
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// 获取工件图标
function getArtifactIcon(type: ArtifactType) {
  switch (type) {
    case 'code':
      return FileCode;
    case 'document':
      return FileText;
    case 'html':
      return Globe;
    case 'pdf':
      return FileSpreadsheet;
    case 'image':
      return Image;
    case 'video':
      return Video;
    case 'binary':
    default:
      return File;
  }
}

// 代码预览组件
const CodePreview: React.FC<{ content: string; language?: string }> = ({ content, language }) => {
  return (
    <div className="relative h-full">
      <pre
        className={cn(
          'h-full overflow-auto p-4 rounded-lg',
          'bg-gray-950 text-gray-100',
          'font-mono text-sm leading-relaxed',
          'scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent',
        )}
      >
        <code className={language ? `language-${language}` : ''}>{content}</code>
      </pre>
    </div>
  );
};

// HTML 预览组件
const HtmlPreview: React.FC<{ url: string }> = ({ url }) => {
  return (
    <div className="h-full w-full rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700">
      <iframe src={url} className="w-full h-full bg-white" sandbox="allow-scripts" title="HTML Preview" />
    </div>
  );
};

// 图片预览组件
const ImagePreview: React.FC<{ url: string; filename: string }> = ({ url, filename }) => {
  return (
    <div className="h-full w-full flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-lg">
      <img src={url} alt={filename} className="max-w-full max-h-full object-contain" />
    </div>
  );
};

// 文档预览组件
const DocumentPreview: React.FC<{ content: string }> = ({ content }) => {
  return (
    <div
      className={cn(
        'h-full overflow-auto p-6 rounded-lg',
        'bg-white dark:bg-gray-800',
        'prose prose-sm dark:prose-invert max-w-none',
        'scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600 scrollbar-track-transparent',
      )}
    >
      <pre className="whitespace-pre-wrap font-sans text-gray-800 dark:text-gray-200">{content}</pre>
    </div>
  );
};

// 无法预览组件
const NoPreview: React.FC<{
  artifact: Artifact;
  onDownload: () => void;
  t: ReturnType<typeof useTranslations>;
}> = ({ artifact, onDownload, t }) => {
  const Icon = getArtifactIcon(artifact.type as ArtifactType);

  return (
    <div className="h-full flex flex-col items-center justify-center gap-4 text-center p-8">
      <div className="w-20 h-20 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
        <Icon className="w-10 h-10 text-gray-400 dark:text-gray-500" />
      </div>
      <div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">{artifact.filename}</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('noPreview')}</p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{t('downloadHint')}</p>
      </div>
      <Button onClick={onDownload} className="mt-2">
        <Download className="w-4 h-4 mr-2" />
        {t('download')}
      </Button>
    </div>
  );
};

const ArtifactPreview: React.FC<ArtifactPreviewProps> = ({ artifact, open, onClose }) => {
  const t = useTranslations('artifacts');
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview');
  const [deployModalOpen, setDeployModalOpen] = useState(false);

  // 加载文件内容
  useEffect(() => {
    if (!artifact || !open) {
      setContent('');
      return;
    }

    const loadContent = async () => {
      // 只有代码和文档类型需要加载文本内容
      if (!['code', 'document'].includes(artifact.type)) {
        return;
      }

      setLoading(true);
      try {
        const response = await fetch(getStorageUrl(artifact.preview_url));
        const text = await response.text();
        setContent(text);
      } catch (error) {
        console.error('Failed to load content:', error);
        setContent('Failed to load content');
      } finally {
        setLoading(false);
      }
    };

    loadContent();
  }, [artifact, open]);

  // 复制代码
  const handleCopy = async () => {
    if (!content) return;
    try {
      await writeToClipboard(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  // 下载文件
  const handleDownload = async () => {
    if (!artifact) return;
    try {
      const response = await fetch(artifact.download_url);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = getDownloadFilename(artifact.filename);
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  // 在新标签页打开
  const handleOpenInNewTab = () => {
    if (!artifact) return;
    window.open(getStorageUrl(artifact.preview_url), '_blank');
  };

  if (!artifact) return null;

  const Icon = getArtifactIcon(artifact.type as ArtifactType);
  const canPreviewContent = ['code', 'document'].includes(artifact.type);
  const isHtml = artifact.type === 'html';
  const isImage = artifact.type === 'image';
  const isPdf =
    artifact.type === 'pdf' ||
    artifact.content_type === 'application/pdf' ||
    artifact.filename.toLowerCase().endsWith('.pdf');
  const cannotPreview = ['binary'].includes(artifact.type);

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent
        className={cn(
          'max-w-5xl w-[90vw] h-[80vh] flex flex-col p-0 gap-0',
          'bg-white dark:bg-gray-900',
          'border border-gray-200 dark:border-gray-700',
        )}
      >
        {/* 头部 */}
        <DialogHeader className="flex-shrink-0 px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                <Icon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </div>
              <div>
                <DialogTitle className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {artifact.filename}
                </DialogTitle>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-gray-500 dark:text-gray-400">{t(`types.${artifact.type}`)}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-500">·</span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">{formatBytes(artifact.size)}</span>
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex items-center gap-2">
              {(isHtml || artifact.type === 'code') && (
                <Button variant="outline" size="sm" onClick={() => setDeployModalOpen(true)} className="text-primary border-primary hover:bg-primary/10">
                  <Globe className="w-4 h-4 mr-1.5" />
                  Deploy to Web
                </Button>
              )}
              {canPreviewContent && (
                <Button variant="ghost" size="sm" onClick={handleCopy} className="text-gray-600 dark:text-gray-400">
                  {copied ? (
                    <>
                      <Check className="w-4 h-4 mr-1.5" />
                      {t('copied')}
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4 mr-1.5" />
                      {t('copyCode')}
                    </>
                  )}
                </Button>
              )}
              {(isHtml || isImage) && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleOpenInNewTab}
                  className="text-gray-600 dark:text-gray-400"
                >
                  <ExternalLink className="w-4 h-4 mr-1.5" />
                  {t('openInNewTab')}
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={handleDownload}>
                <Download className="w-4 h-4 mr-1.5" />
                {t('download')}
              </Button>
            </div>
          </div>
        </DialogHeader>

        {/* 内容区域 */}
        <div className="flex-1 overflow-hidden p-4">
          {loading ? (
            <div className="h-full flex items-center justify-center">
              <div className="animate-spin w-8 h-8 border-2 border-gray-300 dark:border-gray-600 border-t-primary rounded-full" />
            </div>
          ) : cannotPreview ? (
            <NoPreview artifact={artifact} onDownload={handleDownload} t={t} />
          ) : canPreviewContent ? (
            <Tabs
              value={activeTab}
              onValueChange={(v) => setActiveTab(v as 'preview' | 'code')}
              className="h-full flex flex-col"
            >
              <TabsList className="flex-shrink-0 mb-4">
                <TabsTrigger value="preview">{t('preview')}</TabsTrigger>
                <TabsTrigger value="code">{t('code')}</TabsTrigger>
              </TabsList>
              <TabsContent value="preview" className="flex-1 mt-0 overflow-hidden">
                {artifact.type === 'code' ? (
                  <CodePreview content={content} language={artifact.language} />
                ) : (
                  <DocumentPreview content={content} />
                )}
              </TabsContent>
              <TabsContent value="code" className="flex-1 mt-0 overflow-hidden">
                <CodePreview content={content} language={artifact.language} />
              </TabsContent>
            </Tabs>
          ) : isPdf ? (
            <PdfPreviewDynamic url={getStorageUrl(artifact.preview_url)} filename={artifact.filename} />
          ) : isHtml ? (
            <HtmlPreview url={getStorageUrl(artifact.preview_url)} />
          ) : isImage ? (
            <ImagePreview url={getStorageUrl(artifact.preview_url)} filename={artifact.filename} />
          ) : null}
        </div>
      </DialogContent>
      <DeployModal 
        artifact={artifact} 
        open={deployModalOpen} 
        onClose={() => setDeployModalOpen(false)} 
      />
    </Dialog>
  );
};

export default ArtifactPreview;
