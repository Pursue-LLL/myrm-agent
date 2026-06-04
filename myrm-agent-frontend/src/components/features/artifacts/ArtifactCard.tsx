'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Artifact, ArtifactType } from '@/store/chat/types';
import { ChevronDown, ChevronUp, Copy, Download, ExternalLink, Eye, FolderOpen, Globe, Play } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { getStorageUrl } from '@/lib/api';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import {
  deploymentHostname,
  formatBytes,
  getArtifactIcon,
  getDownloadFilename,
  isDeployableArtifactType,
  patchArtifactDeploymentInChat,
} from './artifactUtils';
import { DeployModal, type DeployedArtifactUpdate } from './DeployModal';
import { HtmlPreview } from './renderers/MediaPreview';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { apiRequest } from '@/lib/api';
import { toast } from 'sonner';

interface ArtifactCardProps {
  artifact: Artifact;
  onPreview?: (artifact: Artifact) => void;
  onDownload?: (artifact: Artifact) => void;
}

function getArtifactColor(type: ArtifactType): string {
  switch (type) {
    case 'code':
      return 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20';
    case 'document':
      return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20';
    case 'html':
      return 'text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/20';
    case 'pdf':
      return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20';
    case 'image':
    case 'svg':
      return 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/20';
    case 'mermaid':
      return 'text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-900/20';
    case 'binary':
    default:
      return 'text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/20';
  }
}

function isPreviewable(type: ArtifactType): boolean {
  return ['code', 'document', 'html', 'image', 'svg', 'mermaid', 'pdf'].includes(type);
}

function isCopyable(type: ArtifactType): boolean {
  return ['code', 'document', 'html', 'svg', 'mermaid'].includes(type);
}

function supportsInlinePreview(type: ArtifactType): boolean {
  return type === 'html';
}

const ArtifactCard: React.FC<ArtifactCardProps> = ({ artifact, onPreview, onDownload }) => {
  const t = useTranslations('artifacts');
  const Icon = getArtifactIcon(artifact.type as ArtifactType, artifact.filename);
  const colorClass = getArtifactColor(artifact.type as ArtifactType);
  const canPreview = isPreviewable(artifact.type as ArtifactType);
  const canCopy = isCopyable(artifact.type as ArtifactType);
  const canInlinePreview = supportsInlinePreview(artifact.type as ArtifactType);
  const [copied, setCopied] = useState(false);
  const [pathCopied, setPathCopied] = useState(false);
  const [inlineExpanded, setInlineExpanded] = useState(false);
  const [inlineContent, setInlineContent] = useState<string | null>(null);
  const [inlineLoading, setInlineLoading] = useState(false);
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [artifactState, setArtifactState] = useState(artifact);
  const hasLocalPath = Boolean(artifact.file_path);
  const canDeploy = isDeployableArtifactType(artifact.type as ArtifactType);

  useEffect(() => {
    setArtifactState(artifact);
  }, [artifact]);

  const preloadTimerRef = useRef<NodeJS.Timeout | null>(null);
  const { getCachedContent, setCachedContent } = useArtifactPortalStore();

  const fetchHtmlContent = useCallback(async (): Promise<string | null> => {
    const cached = getCachedContent(artifact.id);
    if (cached) return cached;

    try {
      const fullUrl = getStorageUrl(artifact.preview_url);
      const response = await fetch(fullUrl);
      if (response.ok) {
        const text = await response.text();
        setCachedContent(artifact.id, text);
        return text;
      }
    } catch {
      // fetch failure handled by caller
    }
    return null;
  }, [artifact.id, artifact.preview_url, getCachedContent, setCachedContent]);

  const toggleInlinePreview = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      if (inlineExpanded) {
        setInlineExpanded(false);
        return;
      }

      if (inlineContent) {
        setInlineExpanded(true);
        return;
      }

      setInlineLoading(true);
      setInlineExpanded(true);
      const content = await fetchHtmlContent();
      setInlineContent(content);
      setInlineLoading(false);
    },
    [inlineExpanded, inlineContent, fetchHtmlContent],
  );

  const preloadContent = useCallback(async () => {
    if (!['code', 'document', 'svg', 'mermaid', 'html'].includes(artifact.type)) {
      return;
    }
    if (getCachedContent(artifact.id)) return;

    try {
      const fullUrl = getStorageUrl(artifact.preview_url);
      const response = await fetch(fullUrl);
      if (response.ok) {
        const text = await response.text();
        setCachedContent(artifact.id, text);
      }
    } catch {
      // silent preload failure
    }
  }, [artifact, getCachedContent, setCachedContent]);

  const handleMouseEnter = useCallback(() => {
    preloadTimerRef.current = setTimeout(() => {
      preloadContent();
    }, 200);
  }, [preloadContent]);

  const handleMouseLeave = useCallback(() => {
    if (preloadTimerRef.current) {
      clearTimeout(preloadTimerRef.current);
      preloadTimerRef.current = null;
    }
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      const cached = getCachedContent(artifact.id);
      let text = cached;
      if (!text) {
        const fullUrl = getStorageUrl(artifact.preview_url);
        const response = await fetch(fullUrl);
        if (response.ok) {
          text = await response.text();
          setCachedContent(artifact.id, text);
        }
      }
      if (text) {
        await writeToClipboard(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // clipboard API may fail in insecure context
    }
  }, [artifact, getCachedContent, setCachedContent]);

  const handleOpenInNewTab = useCallback(() => {
    const fullUrl = getStorageUrl(artifact.preview_url);
    window.open(fullUrl, '_blank', 'noopener,noreferrer');
  }, [artifact]);

  const handleRevealInFileManager = useCallback(async () => {
    if (!artifact.file_path) return;
    try {
      if (isTauriRuntime()) {
        const { open } = await import('@tauri-apps/plugin-shell');
        const path = artifact.file_path;
        const parentDir = path.substring(0, path.lastIndexOf('/')) || path.substring(0, path.lastIndexOf('\\'));
        await open(parentDir);
      } else {
        await apiRequest(`/files/${artifact.id}/reveal`, { method: 'POST' });
      }
    } catch {
      toast.error(t('errors.serverError'));
    }
  }, [artifact, t]);

  const handleOpenWithDefaultApp = useCallback(async () => {
    if (!artifact.file_path) return;
    try {
      if (isTauriRuntime()) {
        const { open } = await import('@tauri-apps/plugin-shell');
        await open(artifact.file_path);
      } else {
        await apiRequest(`/files/${artifact.id}/open`, { method: 'POST' });
      }
    } catch {
      toast.error(t('errors.serverError'));
    }
  }, [artifact, t]);

  const handleCopyPath = useCallback(async () => {
    if (!artifact.file_path) return;
    await writeToClipboard(artifact.file_path);
    setPathCopied(true);
    setTimeout(() => setPathCopied(false), 2000);
  }, [artifact.file_path]);

  const handleDownload = async () => {
    if (onDownload) {
      onDownload(artifactState);
      return;
    }

    try {
      const response = await fetch(artifactState.download_url);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = getDownloadFilename(artifactState.filename);
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  const handleDeployed = (update: DeployedArtifactUpdate) => {
    setArtifactState((prev) => ({ ...prev, ...update }));
    patchArtifactDeploymentInChat(artifact.id, update);
  };

  return (
    <>
    <div
      className={cn(
        'group relative rounded-xl overflow-hidden',
        'border border-gray-200/60 dark:border-gray-700/60',
        'bg-gradient-to-br from-white to-gray-50/50 dark:from-gray-800 dark:to-gray-850/50',
        'hover:border-gray-300 dark:hover:border-gray-600',
        'hover:shadow-md hover:shadow-gray-200/50 dark:hover:shadow-gray-900/50',
        'transition-all duration-200 ease-out',
        canInlinePreview && inlineExpanded && 'sm:col-span-2',
      )}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Card header */}
      <div className="flex items-center gap-3 p-3 cursor-pointer" onClick={() => canPreview && onPreview?.(artifact)}>
        <div className={cn('flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center', colorClass)}>
          <Icon className="w-5 h-5" />
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{artifactState.filename}</h4>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className="text-xs text-gray-500 dark:text-gray-400">{t(`types.${artifactState.type}`)}</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">·</span>
            <span className="text-xs text-gray-500 dark:text-gray-400">{formatBytes(artifactState.size)}</span>
            {artifactState.filename.endsWith('.skill') && (
              <>
                <span className="text-xs text-gray-400 dark:text-gray-500">·</span>
                <span className="text-xs text-gray-500 dark:text-gray-400">{t('skillActions.skillPackageHint')}</span>
              </>
            )}
          </div>
          {hasLocalPath && (
            <p
              className="text-[10px] text-gray-400 dark:text-gray-500 truncate mt-0.5 max-w-[200px]"
              title={artifact.file_path}
            >
              {artifact.file_path}
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity duration-200">
          {hasLocalPath && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              onClick={(e) => {
                e.stopPropagation();
                handleOpenWithDefaultApp();
              }}
              title={t('openWithDefaultApp')}
            >
              <Play className="w-4 h-4" />
            </Button>
          )}
          {hasLocalPath && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              onClick={(e) => {
                e.stopPropagation();
                handleRevealInFileManager();
              }}
              title={t('revealInFileManager')}
            >
              <FolderOpen className="w-4 h-4" />
            </Button>
          )}
          {hasLocalPath && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              onClick={(e) => {
                e.stopPropagation();
                handleCopyPath();
              }}
              title={pathCopied ? t('copied') : t('copyPath')}
            >
              <Copy className={cn('w-3.5 h-3.5', pathCopied && 'text-green-500')} />
            </Button>
          )}
          {canDeploy && artifactState.deployment_status === 'READY' && artifactState.deployment_url && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-green-600 dark:text-green-500"
              onClick={(e) => {
                e.stopPropagation();
                window.open(artifactState.deployment_url!, '_blank');
              }}
              title={t('deploy.deployedLabel', { hostname: deploymentHostname(artifactState.deployment_url) })}
            >
              <ExternalLink className="w-4 h-4" />
            </Button>
          )}
          {canDeploy && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-primary"
              onClick={(e) => {
                e.stopPropagation();
                setDeployModalOpen(true);
              }}
              title={t('deploy.openModal')}
            >
              <Globe className="w-4 h-4" />
            </Button>
          )}
          {canInlinePreview && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              onClick={toggleInlinePreview}
              title={inlineExpanded ? t('inlinePreview.collapse') : t('inlinePreview.expand')}
            >
              {inlineExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </Button>
          )}
          {canPreview && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              onClick={(e) => {
                e.stopPropagation();
                onPreview?.(artifact);
              }}
              title={t('preview')}
            >
              <Eye className="w-4 h-4" />
            </Button>
          )}
          {canCopy && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              onClick={(e) => {
                e.stopPropagation();
                handleCopy();
              }}
              title={copied ? t('copied') : t('copyCode')}
            >
              <Copy className={cn('w-4 h-4', copied && 'text-green-500')} />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            onClick={(e) => {
              e.stopPropagation();
              handleOpenInNewTab();
            }}
            title={t('openInNewTab')}
          >
            <ExternalLink className="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            onClick={(e) => {
              e.stopPropagation();
              handleDownload();
            }}
            title={t('download')}
          >
            <Download className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Inline HTML preview */}
      {canInlinePreview && inlineExpanded && (
        <div className="border-t border-gray-200/60 dark:border-gray-700/60">
          {inlineLoading && !inlineContent ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin w-5 h-5 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
            </div>
          ) : inlineContent ? (
            <div className="min-h-[100px]">
              <HtmlPreview content={inlineContent} autoHeight injectTheme />
            </div>
          ) : (
            <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
              {t('inlinePreview.loadError')}
            </div>
          )}
        </div>
      )}
    </div>
    <DeployModal
      artifact={artifactState}
      open={deployModalOpen}
      onClose={() => setDeployModalOpen(false)}
      onDeployed={handleDeployed}
    />
    </>
  );
};

export default ArtifactCard;
