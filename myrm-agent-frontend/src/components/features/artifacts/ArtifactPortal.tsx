'use client';

/**
 * [INPUT]
 * useArtifactPortalStore::{useActiveTab, actions} (POS: Portal 标签、缓存、`diffPreviewTruncated`);
 * ArtifactRenderer / PortalTabs / PortalHeader / VersionHistoryBanner (POS: Artifact 预览子树);
 * next-intl `artifacts`（含 `diffTruncatedNotice`）。
 * [OUTPUT] ArtifactPortal: 侧栏宿主；在 `activeTab.diffPreviewTruncated` 时展示单行截断说明条。
 * [POS] Artifact 预览入口容器；协调加载、手势、快捷键与 Diff 截断 UX。
 */

import React, { useEffect, useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { DragDropVerticalIcon } from 'hugeicons-react';
import { Info } from 'lucide-react';
import type { PickedElement } from './renderers/MediaPreview';
import useArtifactPortalStore, {
  ArtifactErrorType,
  parseErrorFromResponse,
  parseNetworkError,
  // Selector hooks for optimized rendering
  useIsPortalOpen,
  useCurrentArtifact,
  useArtifactContent,
  useArtifactLoading,
  useArtifactError,
  useIsGenerating,
  useDisplayMode,
  usePanelWidth,
  useOpenTabs,
  useArtifactVersions,
  useViewingVersionIndex,
  useActiveTab,
} from '@/store/useArtifactPortalStore';
import ArtifactRenderer from './ArtifactRenderer';
import { formatBytes, getDownloadFilename } from './artifactUtils';
import { getStorageUrl } from '@/lib/api';
import { MOBILE_BREAKPOINT, SWIPE_MAX_OFFSET } from '@/lib/constants/artifact';

// 拆分的子组件
import PortalHeader from './portal/PortalHeader';
import PortalTabs from './portal/PortalTabs';
import PortalErrorDisplay from './portal/PortalErrorDisplay';
import ElementPickerToolbar from './portal/ElementPickerToolbar';
import { VersionHistoryBanner } from './portal/VersionHistory';
import { usePortalGestures } from './portal/usePortalGestures';
import { usePortalKeyboard } from './portal/usePortalKeyboard';
import { useScrollLock } from '@/hooks/useScrollLock';
import { useArtifactVersionsFromHistory } from '@/hooks/useArtifactVersionsFromHistory';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

/** 检测是否为移动端 */
const useIsMobile = () => {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  return isMobile;
};

/** Portal 侧边面板组件 */
const ArtifactPortal: React.FC = () => {
  const t = useTranslations('artifacts');

  // 使用 selector hooks 优化渲染性能
  const isOpen = useIsPortalOpen();
  const currentArtifact = useCurrentArtifact();
  const content = useArtifactContent();
  const contentLoading = useArtifactLoading();
  const error = useArtifactError();
  const isGenerating = useIsGenerating();
  const displayMode = useDisplayMode();
  const panelWidth = usePanelWidth();
  const { tabs: openTabs, activeIndex: activeTabIndex } = useOpenTabs();
  const viewingVersionIndex = useViewingVersionIndex();
  const activeTab = useActiveTab();

  // 使用从聊天历史中解析的版本列表
  const historyVersions = useArtifactVersionsFromHistory(currentArtifact?.id);
  const storeVersions = useArtifactVersions();
  const versions = historyVersions.length > 0 ? historyVersions : storeVersions;

  // Actions 只需要在需要时获取
  const {
    closePortal,
    setDisplayMode,
    setContent,
    setContentLoading,
    setError,
    clearError,
    setPanelWidth,
    closeTab,
    switchTab,
    closeOtherTabs,
    closeAllTabs,
    switchToVersion,
    rollbackToVersion,
  } = useArtifactPortalStore();

  const [copied, setCopied] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pickerMode, setPickerMode] = useState(false);
  const [pickedElement, setPickedElement] = useState<PickedElement | null>(null);
  const isMobile = useIsMobile();
  const portalRef = useRef<HTMLDivElement>(null);

  // Prevent scroll penetration when portal is open
  // 防止弹窗打开时的滚动穿透
  useScrollLock(isOpen);

  // 包装 switchToVersion 以支持历史版本内容
  const handleSwitchVersion = useCallback(
    (index: number) => {
      if (index === -1) {
        switchToVersion(-1);
      } else if (versions[index]) {
        switchToVersion(index, versions[index].content);
      }
    },
    [switchToVersion, versions],
  );

  const handleRollbackVersion = useCallback(
    (index: number) => {
      if (versions[index]) {
        rollbackToVersion(index, versions[index].content);
      }
    },
    [rollbackToVersion, versions],
  );
  const { swipeOffset, isSwiping, handleTouchStart, handleTouchMove, handleTouchEnd, isDragging, handleDragStart } =
    usePortalGestures({
      isMobile,
      panelWidth,
      onClose: closePortal,
      onSetPanelWidth: setPanelWidth,
    });

  // 加载内容
  const loadContent = useCallback(async () => {
    if (!currentArtifact || !isOpen) {
      setContent('');
      return;
    }

    // 需要加载内容的类型：代码、文档、SVG、Mermaid、HTML
    // HTML 类型需要内容用于 Blob URL 渲染（当 preview_url 不可用时）
    const typesNeedContent = ['code', 'document', 'svg', 'mermaid', 'html'];
    if (!typesNeedContent.includes(currentArtifact.type)) {
      setContentLoading(false);
      return;
    }

    if (content && content.length > 0) {
      setContentLoading(false);
      return;
    }
    if (!currentArtifact.preview_url) {
      setContentLoading(false);
      return;
    }

    setContentLoading(true);
    clearError();

    try {
      const fullUrl = getStorageUrl(currentArtifact.preview_url);
      const response = await fetch(fullUrl);

      if (!response.ok) {
        let errorBody: string | undefined;
        try {
          errorBody = await response.text();
        } catch {
          /* ignore */
        }
        const artifactError = parseErrorFromResponse(response.status, response.statusText, errorBody);
        setError(artifactError);
        return;
      }

      const text = await response.text();
      setContent(text);
    } catch (err) {
      console.error('Failed to load content:', err);
      if (err instanceof Error) {
        setError(parseNetworkError(err));
      } else {
        setError({
          type: ArtifactErrorType.Unknown,
          messageKey: 'errors.unknown',
          retryable: true,
        });
      }
    } finally {
      setContentLoading(false);
    }
  }, [currentArtifact, isOpen, content, setContent, setContentLoading, setError, clearError]);

  useEffect(() => {
    loadContent();
  }, [loadContent]);

  // 复制内容
  const handleCopy = useCallback(async () => {
    if (!content) return;
    try {
      await writeToClipboard(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  }, [content]);

  // 下载文件
  const handleDownload = useCallback(async () => {
    if (!currentArtifact) return;
    try {
      const fullUrl = getStorageUrl(currentArtifact.download_url);
      const response = await fetch(fullUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
  }, [currentArtifact]);

  // 在新标签页打开
  const handleOpenInNewTab = useCallback(() => {
    if (!currentArtifact) return;
    window.open(getStorageUrl(currentArtifact.preview_url), '_blank', 'noopener,noreferrer');
  }, [currentArtifact]);

  // 切换全屏
  const toggleFullscreen = useCallback(() => setIsFullscreen((prev) => !prev), []);

  // 重试加载
  const handleRetry = useCallback(() => {
    clearError();
    loadContent();
  }, [clearError, loadContent]);

  const handleElementPick = useCallback((el: PickedElement) => {
    setPickedElement(el);
    setPickerMode(false);
  }, []);

  const handlePickerDismiss = useCallback(() => {
    setPickedElement(null);
    setPickerMode(false);
  }, []);

  // 键盘快捷键
  usePortalKeyboard({
    isOpen,
    isFullscreen,
    displayMode,
    content,
    openTabsLength: openTabs.length,
    activeTabIndex,
    onClose: closePortal,
    onSetFullscreen: setIsFullscreen,
    onSetDisplayMode: setDisplayMode,
    onDownload: handleDownload,
    onCloseTab: closeTab,
    onSwitchTab: switchTab,
    onCopy: handleCopy,
    onCloseAllTabs: closeAllTabs,
  });

  useEffect(() => {
    setPickerMode(false);
    setPickedElement(null);
  }, [activeTabIndex]);

  // 打开 Portal 时自动聚焦
  useEffect(() => {
    if (isOpen && portalRef.current) {
      const timer = setTimeout(() => portalRef.current?.focus(), 100);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // 获取错误提示
  const getErrorHint = useCallback(() => {
    if (!error) return '';
    switch (error.type) {
      case ArtifactErrorType.NotFound:
        return t('errors.notFoundHint');
      case ArtifactErrorType.ServerError:
        return t('errors.serverErrorHint');
      case ArtifactErrorType.NetworkError:
        return t('errors.networkErrorHint');
      case ArtifactErrorType.PermissionDenied:
        return t('errors.permissionDeniedHint');
      default:
        return '';
    }
  }, [error, t]);

  if (!isOpen || !currentArtifact) return null;

  const canPreviewContent = ['code', 'document', 'svg', 'mermaid', 'html'].includes(currentArtifact.type);
  const isHtml = currentArtifact.type === 'html';
  const isImage = currentArtifact.type === 'image';
  const effectiveFullscreen = isFullscreen || isMobile;

  // 提取 lineRange (从 UI 状态中提取，而不是 Artifact 领域模型)
  const lineRange = activeTab?.lineRange;

  return (
    <>
      {/* 背景遮罩 - 完全 overlay 模式 */}
      {isOpen && (
        <div
          className={cn(
            'fixed inset-0 z-40 animate-in fade-in-0 duration-200',
            // 全屏/移动端：深色遮罩；PC 端非全屏：中等遮罩（提升可见性）
            effectiveFullscreen ? 'bg-black/50' : 'bg-black/30',
          )}
          onClick={() => {
            // 移动端：关闭弹窗；PC 端全屏：退出全屏；PC 端非全屏：关闭弹窗
            if (isMobile || !effectiveFullscreen) {
              closePortal();
            } else {
              setIsFullscreen(false);
            }
          }}
          aria-hidden="true"
        />
      )}

      {/* Portal 侧边面板 */}
      <div
        ref={portalRef}
        className={cn(
          'flex flex-col bg-background shadow-xl focus:outline-none',
          isDragging || isSwiping ? '' : 'transition-all duration-500',
          isMobile
            ? cn(
                'fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border-t max-h-[85vh]',
                isOpen ? 'translate-y-0' : 'translate-y-full',
              )
            : cn(
                'fixed top-0 right-0 h-full z-40 border-l border-border',
                effectiveFullscreen ? 'inset-4 rounded-xl shadow-2xl border border-border z-50' : '',
                isOpen ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0 pointer-events-none',
              ),
        )}
        style={{
          transitionTimingFunction: isOpen ? 'cubic-bezier(0.34, 1.56, 0.64, 1)' : 'cubic-bezier(0.36, 0, 0.66, -0.56)',
          width: effectiveFullscreen || isMobile ? undefined : `${panelWidth}px`,
          transform: isMobile && swipeOffset > 0 ? `translateY(${swipeOffset}px)` : undefined,
          opacity: isMobile && swipeOffset > 0 ? 1 - (swipeOffset / SWIPE_MAX_OFFSET) * 0.5 : undefined,
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        role="dialog"
        aria-modal="true"
        aria-label={`${t('preview')}: ${currentArtifact.filename}`}
        tabIndex={-1}
      >
        {/* 无障碍描述 */}
        <span id="artifact-portal-description" className="sr-only">
          {`正在预览文件 ${currentArtifact.filename}，类型为 ${currentArtifact.type}，大小 ${formatBytes(currentArtifact.size)}。按 ESC 键关闭。`}
        </span>

        {/* 移动端拖拽指示条 */}
        {isMobile && (
          <div className="flex justify-center py-2 cursor-grab active:cursor-grabbing touch-none">
            <div
              className={cn(
                'w-12 h-1.5 rounded-full transition-colors',
                swipeOffset > 50 ? 'bg-primary/50' : 'bg-muted-foreground/30',
              )}
            />
          </div>
        )}

        {/* 标签页栏 */}
        <PortalTabs
          tabs={openTabs.map((tab) => ({ artifact: tab.artifact, isGenerating: tab.isGenerating }))}
          activeIndex={activeTabIndex}
          onSwitchTab={switchTab}
          onCloseTab={closeTab}
          onCloseOtherTabs={closeOtherTabs}
          onCloseAllTabs={closeAllTabs}
          labels={{
            close: t('tabs.close'),
            closeOthers: t('tabs.closeOthers'),
            closeAll: t('tabs.closeAll'),
            generating: t('tabs.generating'),
          }}
        />

        {/* 拖拽调整宽度手柄 */}
        {!effectiveFullscreen && !isMobile && (
          <div
            className={cn(
              'absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize z-10',
              'hover:bg-primary/20 active:bg-primary/30 transition-colors',
              'group flex items-center justify-center',
              isDragging && 'bg-primary/30',
            )}
            onMouseDown={handleDragStart}
          >
            <div className={cn('opacity-0 group-hover:opacity-100 transition-opacity', isDragging && 'opacity-100')}>
              <DragDropVerticalIcon className="w-3 h-3 text-muted-foreground" />
            </div>
          </div>
        )}

        {/* 头部 */}
        <PortalHeader
          artifact={currentArtifact}
          displayMode={displayMode}
          isGenerating={isGenerating}
          isMobile={isMobile}
          isFullscreen={isFullscreen}
          copied={copied}
          canPreviewContent={canPreviewContent}
          isHtml={isHtml}
          isImage={isImage}
          pickerMode={pickerMode}
          versions={versions}
          viewingVersionIndex={viewingVersionIndex}
          onSetDisplayMode={setDisplayMode}
          onCopy={handleCopy}
          onDownload={handleDownload}
          onOpenInNewTab={handleOpenInNewTab}
          onToggleFullscreen={toggleFullscreen}
          onClose={closePortal}
          onTogglePicker={() => { setPickerMode((p) => !p); setPickedElement(null); }}
          onSwitchVersion={handleSwitchVersion}
          onRollbackVersion={handleRollbackVersion}
          labels={{
            preview: t('preview'),
            code: t('code'),
            copied: t('copied'),
            copyCode: t('copyCode'),
            openInNewTab: t('openInNewTab'),
            download: t('download'),
            close: t('close'),
            generating: t('tabs.generating'),
            type: (type: string) => t(`types.${type}`),
            elementPicker: t('elementPicker.toggle'),
          }}
        />

        {/* 历史版本查看提示条 */}
        <VersionHistoryBanner
          versions={versions}
          viewingIndex={viewingVersionIndex}
          onBackToLatest={() => switchToVersion(-1)}
        />

        {activeTab?.diffPreviewTruncated && (
          <div
            role="status"
            className={cn(
              'shrink-0 text-xs py-1.5 px-3 flex items-start gap-1.5 border-b',
              'bg-sky-100/90 dark:bg-sky-950/40 text-sky-950 dark:text-sky-100',
              'border-sky-200 dark:border-sky-800',
            )}
          >
            <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden />
            <span>{t('diffTruncatedNotice')}</span>
          </div>
        )}

        {/* 内容区域 */}
        <div className="flex-1 overflow-hidden" id="artifact-content-container">
          {error ? (
            <PortalErrorDisplay
              error={error}
              onRetry={handleRetry}
              labels={{
                message: t(error.messageKey, error.messageParams),
                httpStatus: t('errors.httpStatus'),
                retry: t('retry'),
                hint: getErrorHint(),
              }}
            />
          ) : (
            <div className="relative h-full">
              <ArtifactRenderer
                artifact={currentArtifact}
                content={content}
                displayMode={displayMode}
                loading={contentLoading}
                onDownload={handleDownload}
                pickerMode={pickerMode}
                onElementPick={handleElementPick}
              />

              {/* 行号滚动逻辑 */}
              {!contentLoading && lineRange && <LineRangeScroller lineRange={lineRange} content={content} />}

              {/* 实时生成进度指示器 */}
              {isGenerating && (
                <div className="absolute bottom-0 left-0 right-0 z-10">
                  <div className="h-1 bg-muted overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-primary via-primary/50 to-primary"
                      style={{ animation: 'progress-bar 1.5s ease-in-out infinite' }}
                    />
                  </div>
                  <div className="flex items-center justify-center gap-2 py-2 bg-background/95 backdrop-blur-sm border-t border-border text-xs text-muted-foreground">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                    </span>
                    {t('tabs.generating')}
                  </div>
                </div>
              )}

              {/* Element picker toolbar */}
              {isHtml && displayMode === ArtifactDisplayMode.Preview && (
                <ElementPickerToolbar
                  pickedElement={pickedElement}
                  artifactId={currentArtifact.id}
                  onDismiss={handlePickerDismiss}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

// 辅助组件：处理行号滚动和高亮
const LineRangeScroller: React.FC<{ lineRange: string; content: string }> = ({ lineRange, content }) => {
  useEffect(() => {
    if (!lineRange || !content) return;

    // 解析行号，例如 "10-20" 或 "10-"
    const parts = lineRange.split('-');
    const startLine = parseInt(parts[0], 10);
    if (isNaN(startLine)) return;

    // 延迟执行以确保 DOM 已经渲染完毕 (ArtifactRenderer 内部可能使用了异步高亮)
    const timer = setTimeout(() => {
      // O(1) 极速定位目标行
      const targetElement = document.getElementById(`code-line-${startLine}`);

      if (targetElement) {
        // 滚动到目标行
        targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // 添加高亮动画
        const endLine = parts.length > 1 && parts[1] ? parseInt(parts[1], 10) : startLine;
        const validEndLine = isNaN(endLine) ? startLine : endLine;

        // 高亮范围内的所有行
        for (let i = startLine; i <= validEndLine; i++) {
          const rowDiv = document.getElementById(`code-line-${i}`);
          if (rowDiv) {
            // 添加高亮 class，使用 Tailwind 的 bg-yellow-500/20 等
            rowDiv.classList.add('bg-yellow-500/20', 'transition-colors', 'duration-1000');

            // 3秒后移除高亮
            setTimeout(() => {
              rowDiv.classList.remove('bg-yellow-500/20');
            }, 3000);
          }
        }
      }
    }, 300); // 给代码高亮留出时间

    return () => clearTimeout(timer);
  }, [lineRange, content]);

  return null;
};

export default ArtifactPortal;
