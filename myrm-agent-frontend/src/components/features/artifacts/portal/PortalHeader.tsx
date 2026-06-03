'use client';

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  Cancel01Icon,
  Download01Icon,
  Copy01Icon,
  Tick01Icon,
  LinkSquare01Icon,
  CodeIcon,
  ViewIcon,
  Maximize01Icon,
  Minimize01Icon,
} from 'hugeicons-react';
import { Button } from '@/components/primitives/button';
import { Artifact, ArtifactType, ArtifactVersion } from '@/store/chat/types';
import { ArtifactDisplayMode } from '@/store/useArtifactPortalStore';
import { getArtifactIcon, formatBytes } from '../artifactUtils';
import VersionHistory from './VersionHistory';

interface PortalHeaderProps {
  artifact: Artifact;
  displayMode: ArtifactDisplayMode;
  isGenerating: boolean;
  isMobile: boolean;
  isFullscreen: boolean;
  copied: boolean;
  canPreviewContent: boolean;
  isHtml: boolean;
  isImage: boolean;
  /** 版本列表 */
  versions: ArtifactVersion[];
  /** 当前查看的版本索引（-1 表示最新） */
  viewingVersionIndex: number;
  onSetDisplayMode: (mode: ArtifactDisplayMode) => void;
  onCopy: () => void;
  onDownload: () => void;
  onOpenInNewTab: () => void;
  onToggleFullscreen: () => void;
  onClose: () => void;
  /** 切换版本 */
  onSwitchVersion: (index: number) => void;
  /** 回滚版本 */
  onRollbackVersion: (index: number) => void;
  labels: {
    preview: string;
    code: string;
    copied: string;
    copyCode: string;
    openInNewTab: string;
    download: string;
    close: string;
    generating: string;
    type: (type: string) => string;
  };
}

/** Portal 头部工具栏 */
const PortalHeader: React.FC<PortalHeaderProps> = ({
  artifact,
  displayMode,
  isGenerating,
  isMobile,
  isFullscreen,
  copied,
  canPreviewContent,
  isHtml,
  isImage,
  versions,
  viewingVersionIndex,
  onSetDisplayMode,
  onCopy,
  onDownload,
  onOpenInNewTab,
  onToggleFullscreen,
  onClose,
  onSwitchVersion,
  onRollbackVersion,
  labels,
}) => {
  const Icon = getArtifactIcon(artifact.type as ArtifactType, artifact.filename);

  return (
    <div
      className={cn(
        'flex-shrink-0 border-b border-border',
        isMobile ? 'flex flex-col gap-3 px-4 py-3' : 'flex items-center justify-between px-4 py-3',
      )}
    >
      {/* 文件信息 */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
          <Icon className="w-4 h-4 text-muted-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium text-foreground truncate">{artifact.filename}</h3>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span>{labels.type(artifact.type)}</span>
            <span>·</span>
            <span>{formatBytes(artifact.size)}</span>
            {isGenerating && (
              <>
                <span>·</span>
                <span className="inline-flex items-center gap-1 text-primary">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                  </span>
                  {labels.generating}
                </span>
              </>
            )}
          </div>
        </div>
        {isMobile && (
          <Button variant="ghost" size="icon" className="w-8 h-8 flex-shrink-0" onClick={onClose} title={labels.close}>
            <Cancel01Icon className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* 工具栏 */}
      <div
        className={cn('flex items-center', isMobile ? 'gap-2 overflow-x-auto pb-1 -mx-4 px-4 scrollbar-hide' : 'gap-1')}
      >
        {/* 模式切换 */}
        {canPreviewContent && (
          <div className={cn('flex items-center bg-muted rounded-lg p-0.5 flex-shrink-0', !isMobile && 'mr-2')}>
            <button
              onClick={() => onSetDisplayMode(ArtifactDisplayMode.Preview)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap',
                displayMode === ArtifactDisplayMode.Preview
                  ? 'bg-background text-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <ViewIcon className="w-3.5 h-3.5" />
              {labels.preview}
            </button>
            <button
              onClick={() => onSetDisplayMode(ArtifactDisplayMode.Code)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap',
                displayMode === ArtifactDisplayMode.Code
                  ? 'bg-background text-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <CodeIcon className="w-3.5 h-3.5" />
              {labels.code}
            </button>
          </div>
        )}

        {/* 复制按钮 */}
        {canPreviewContent && (
          <Button
            variant="ghost"
            size="icon"
            className="w-8 h-8 flex-shrink-0"
            onClick={onCopy}
            title={copied ? labels.copied : labels.copyCode}
          >
            {copied ? <Tick01Icon className="w-4 h-4 text-green-500" /> : <Copy01Icon className="w-4 h-4" />}
          </Button>
        )}

        {/* 新标签页打开 */}
        {(isHtml || isImage) && (
          <Button
            variant="ghost"
            size="icon"
            className="w-8 h-8 flex-shrink-0"
            onClick={onOpenInNewTab}
            title={labels.openInNewTab}
          >
            <LinkSquare01Icon className="w-4 h-4" />
          </Button>
        )}

        {/* 版本历史 */}
        {versions.length > 0 && (
          <VersionHistory
            versions={versions}
            viewingIndex={viewingVersionIndex}
            isGenerating={isGenerating}
            onSwitchVersion={onSwitchVersion}
            onRollback={onRollbackVersion}
          />
        )}

        {/* 下载按钮 */}
        <Button
          variant="ghost"
          size="icon"
          className="w-8 h-8 flex-shrink-0"
          onClick={onDownload}
          title={labels.download}
        >
          <Download01Icon className="w-4 h-4" />
        </Button>

        {/* 全屏切换 */}
        {!isMobile && (
          <Button variant="ghost" size="icon" className="w-8 h-8 flex-shrink-0" onClick={onToggleFullscreen}>
            {isFullscreen ? <Minimize01Icon className="w-4 h-4" /> : <Maximize01Icon className="w-4 h-4" />}
          </Button>
        )}

        {/* 关闭按钮 */}
        {!isMobile && (
          <Button variant="ghost" size="icon" className="w-8 h-8 flex-shrink-0" onClick={onClose} title={labels.close}>
            <Cancel01Icon className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  );
};

export default PortalHeader;
