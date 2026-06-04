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
  Link2,
  Image,
  Video,
  File,
  FileSpreadsheet,
} from 'lucide-react';
import dynamic from 'next/dynamic';
import { getApiUrl, getStorageUrl } from '@/lib/api';
import {
  buildPublicArtifactShareUrl,
  createArtifactSharePreview,
  deploymentHostname,
  fetchArtifactDeployPreflight,
  getDownloadFilename,
  isDeployCandidateArtifactType,
  isDeploymentStale,
  isSharePreviewableArtifact,
  patchArtifactDeploymentInChat,
  type ArtifactDeployPreflight,
} from './artifactUtils';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { toast } from 'sonner';

import { DeployModal, type DeployedArtifactUpdate } from './DeployModal';

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
  const [currentArtifact, setCurrentArtifact] = useState<Artifact | null>(artifact);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview');
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [deployPreflight, setDeployPreflight] = useState<ArtifactDeployPreflight | null>(null);
  const [shareLoading, setShareLoading] = useState(false);

  useEffect(() => {
    setCurrentArtifact(artifact);
  }, [artifact]);

  const isDeployCandidate = currentArtifact
    ? isDeployCandidateArtifactType(currentArtifact.type as ArtifactType)
    : false;
  const canDeploy = isDeployCandidate && deployPreflight?.deployable === true;
  const canSharePreview = currentArtifact ? isSharePreviewableArtifact(currentArtifact) : false;

  useEffect(() => {
    if (!open || !currentArtifact || !isDeployCandidate) {
      setDeployPreflight(null);
      return;
    }
    let cancelled = false;
    void fetchArtifactDeployPreflight(currentArtifact.id).then((result) => {
      if (!cancelled) {
        setDeployPreflight(result);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [open, currentArtifact?.id, isDeployCandidate]);

  const handleDeployed = (update: DeployedArtifactUpdate) => {
    setCurrentArtifact((prev) => {
      if (!prev) {
        return prev;
      }
      patchArtifactDeploymentInChat(prev.id, update);
      return { ...prev, ...update };
    });
  };

  // Hydrate deployment state from DB when preview opens (survives page refresh)
  useEffect(() => {
    if (!currentArtifact || !open) {
      return;
    }

    let cancelled = false;

    const hydrateDeployment = async () => {
      try {
        const response = await fetch(getApiUrl(`/api/v1/files/artifacts/${currentArtifact.id}`));
        if (!response.ok || cancelled) {
          return;
        }
        const data = (await response.json()) as {
          deployment_url?: string | null;
          deployment_status?: string | null;
          deployment_project_id?: string | null;
          deployment_version_id?: string | null;
          latest_version_id?: string | null;
        };
        if (cancelled) {
          return;
        }
        setCurrentArtifact((prev) =>
          prev
            ? {
                ...prev,
                deployment_url: data.deployment_url ?? prev.deployment_url,
                deployment_status: data.deployment_status ?? prev.deployment_status,
                deployment_project_id: data.deployment_project_id ?? prev.deployment_project_id,
                deployment_version_id: data.deployment_version_id ?? prev.deployment_version_id,
                latest_version_id: data.latest_version_id ?? prev.latest_version_id,
              }
            : prev,
        );
      } catch (error) {
        console.error('Failed to hydrate artifact deployment state:', error);
      }
    };

    void hydrateDeployment();

    return () => {
      cancelled = true;
    };
  }, [currentArtifact?.id, open]);

  // 加载文件内容
  useEffect(() => {
    if (!currentArtifact || !open) {
      setContent('');
      return;
    }

    const loadContent = async () => {
      // 只有代码和文档类型需要加载文本内容
      if (!['code', 'document'].includes(currentArtifact.type)) {
        return;
      }

      setLoading(true);
      try {
        const response = await fetch(getStorageUrl(currentArtifact.preview_url));
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
  }, [currentArtifact, open]);

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
    if (!currentArtifact) return;
    try {
      const response = await fetch(currentArtifact.download_url);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = getDownloadFilename(currentArtifact.filename);
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
    if (!currentArtifact) return;
    window.open(getStorageUrl(currentArtifact.preview_url), '_blank');
  };

  const handleOpenDeploy = () => {
    if (deployPreflight && !deployPreflight.deployable) {
      toast.error(deployPreflight.message, { description: deployPreflight.hint ?? undefined });
      return;
    }
    setDeployModalOpen(true);
  };

  const handleSharePreview = async () => {
    if (!currentArtifact || shareLoading) {
      return;
    }
    setShareLoading(true);
    try {
      const result = await createArtifactSharePreview(currentArtifact.id);
      const url = buildPublicArtifactShareUrl(result.share_path);
      await writeToClipboard(url);
      toast.success(t('sharePreview.successTitle'), {
        description: t('sharePreview.successDescription'),
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('sharePreview.failed');
      toast.error(message);
    } finally {
      setShareLoading(false);
    }
  };

  if (!currentArtifact) return null;

  const Icon = getArtifactIcon(currentArtifact.type as ArtifactType);
  const canPreviewContent = ['code', 'document'].includes(currentArtifact.type);
  const isHtml = currentArtifact.type === 'html';
  const isImage = currentArtifact.type === 'image';
  const isPdf =
    currentArtifact.type === 'pdf' ||
    currentArtifact.content_type === 'application/pdf' ||
    currentArtifact.filename.toLowerCase().endsWith('.pdf');
  const cannotPreview = ['binary'].includes(currentArtifact.type);
  const showRedeployBanner = isDeploymentStale(currentArtifact);

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
                  {currentArtifact.filename}
                </DialogTitle>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-gray-500 dark:text-gray-400">{t(`types.${currentArtifact.type}`)}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-500">·</span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">{formatBytes(currentArtifact.size)}</span>
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex flex-wrap items-center justify-end gap-2 max-w-[min(100%,20rem)] sm:max-w-none">
              {currentArtifact.deployment_status === 'READY' && currentArtifact.deployment_url && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(currentArtifact.deployment_url!, '_blank')}
                  className="text-green-600 dark:text-green-500 border-green-200 dark:border-green-900/50 hover:bg-green-50 dark:hover:bg-green-900/20"
                >
                  <Globe className="w-4 h-4 mr-1.5" />
                  <span className="hidden sm:inline">
                    {t('deploy.deployedLabel', { hostname: deploymentHostname(currentArtifact.deployment_url) })}
                  </span>
                  <ExternalLink className="w-3 h-3 ml-1.5 opacity-50" />
                </Button>
              )}
              {canSharePreview && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={shareLoading}
                  onClick={() => void handleSharePreview()}
                  className="text-primary border-primary/30 hover:bg-primary/10"
                >
                  <Link2 className={cn('w-4 h-4 mr-1.5', shareLoading && 'opacity-50')} />
                  <span className="hidden sm:inline">{t('sharePreview.open')}</span>
                </Button>
              )}
              {isDeployCandidate && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleOpenDeploy}
                  className={cn(
                    'border-primary/30 hover:bg-primary/10',
                    canDeploy ? 'text-primary' : 'text-muted-foreground opacity-70',
                  )}
                >
                  <Globe className="w-4 h-4 mr-1.5" />
                  {t('deploy.openModal')}
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
          {showRedeployBanner && (
            <div className="mb-4 flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 sm:flex-row sm:items-center sm:justify-between dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100">
              <span>{t('deploy.redeployBanner')}</span>
              <Button size="sm" variant="outline" onClick={() => setDeployModalOpen(true)}>
                {t('deploy.redeployAction')}
              </Button>
            </div>
          )}
          {loading ? (
            <div className="h-full flex items-center justify-center">
              <div className="animate-spin w-8 h-8 border-2 border-gray-300 dark:border-gray-600 border-t-primary rounded-full" />
            </div>
          ) : cannotPreview ? (
            <NoPreview artifact={currentArtifact} onDownload={handleDownload} t={t} />
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
                {currentArtifact.type === 'code' ? (
                  <CodePreview content={content} language={currentArtifact.language} />
                ) : (
                  <DocumentPreview content={content} />
                )}
              </TabsContent>
              <TabsContent value="code" className="flex-1 mt-0 overflow-hidden">
                <CodePreview content={content} language={currentArtifact.language} />
              </TabsContent>
            </Tabs>
          ) : isPdf ? (
            <PdfPreviewDynamic url={getStorageUrl(currentArtifact.preview_url)} filename={currentArtifact.filename} />
          ) : isHtml ? (
            <HtmlPreview url={getStorageUrl(currentArtifact.preview_url)} />
          ) : isImage ? (
            <ImagePreview url={getStorageUrl(currentArtifact.preview_url)} filename={currentArtifact.filename} />
          ) : null}
        </div>
      </DialogContent>
      <DeployModal
        artifact={currentArtifact}
        open={deployModalOpen}
        onClose={() => setDeployModalOpen(false)}
        onDeployed={handleDeployed}
      />
    </Dialog>
  );
};

export default ArtifactPreview;
