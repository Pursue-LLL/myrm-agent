'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  SandpackProvider,
  SandpackPreview,
  SandpackCodeEditor,
  SandpackLayout,
  SandpackStack,
} from '@codesandbox/sandpack-react';
import { nightOwl, githubLight } from '@codesandbox/sandpack-themes';
import { Button } from '@/components/primitives/button';
import { Code, Eye, Terminal, SplitSquareHorizontal } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { TAILWIND_CSS, TAILWIND_CONFIG } from './constants/reactPreviewConstants';
import { SandpackErrorBoundary } from './components/SandpackErrorBoundary';
import { SandpackCodeListener } from './components/SandpackCodeListener';
import ConsolePanel from './components/ConsolePanel';
import { useReactPreview } from '@/hooks/useReactPreview';
import useArtifactPortalStore, { useIsGenerating } from '@/store/useArtifactPortalStore';

interface ReactPreviewProps {
  code: string;
  filename: string;
  isDarkMode?: boolean;
  artifactId?: string;
}

/**
 * React 组件预览（增强版）
 */
const ReactPreview = memo<ReactPreviewProps>(({ code, filename, isDarkMode = false, artifactId }) => {
  const t = useTranslations('artifacts');
  const dirtyArtifacts = useArtifactPortalStore((state) => state.dirtyArtifacts);
  const isDirty = artifactId ? !!dirtyArtifacts[artifactId] : false;
  const isGenerating = useIsGenerating();

  // 使用自定义Hook管理状态和逻辑
  const {
    viewMode,
    setViewMode,
    showConsole,
    toggleConsole,
    closeConsole,
    isValid,
    wrappedCode,
    allDependencies,
    errorLabels,
  } = useReactPreview({ code, filename, t });

  // 如果不是有效的 React 代码，显示提示
  if (!isValid) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4 p-6 text-center bg-muted/30">
        <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center">
          <Code className="w-8 h-8 text-muted-foreground" />
        </div>
        <div>
          <p className="font-medium text-foreground">{t('reactPreview.notReactCode')}</p>
          <p className="text-sm text-muted-foreground mt-1">{t('reactPreview.notReactCodeHint')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* 工具栏 */}
      <div className="flex-shrink-0 flex items-center justify-between px-3 py-2 border-b border-border bg-muted/30">
        {/* 视图切换 */}
        <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={viewMode === 'preview' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('preview')}
                className="h-7 px-2 gap-1"
              >
                <Eye className="w-3.5 h-3.5" />
                <span className="text-xs hidden sm:inline">{t('reactPreview.preview')}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{t('reactPreview.preview')}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={viewMode === 'code' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('code')}
                className="h-7 px-2 gap-1"
              >
                <Code className="w-3.5 h-3.5" />
                <span className="text-xs hidden sm:inline">{t('reactPreview.code')}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{t('reactPreview.code')}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={viewMode === 'split' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('split')}
                className="h-7 px-2 gap-1"
              >
                <SplitSquareHorizontal className="w-3.5 h-3.5" />
                <span className="text-xs hidden sm:inline">{t('reactPreview.split')}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{t('reactPreview.split')}</TooltipContent>
          </Tooltip>
        </div>

        <div className="flex items-center gap-2">
          {/* 保存状态指示器 */}
          {artifactId && (
            <span className="text-xs text-muted-foreground mr-2 hidden sm:inline-block">
              {isDirty ? t('reactPreview.saving') : t('reactPreview.saved')}
            </span>
          )}

          {/* 控制台按钮 */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={showConsole ? 'secondary' : 'ghost'}
                size="sm"
                onClick={toggleConsole}
                className="h-7 px-2 gap-1"
              >
                <Terminal className="w-3.5 h-3.5" />
                <span className="text-xs hidden sm:inline">{t('reactPreview.console')}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{t('reactPreview.toggleConsole')}</TooltipContent>
          </Tooltip>

          {/* 文件名 */}
          <span className="text-xs text-muted-foreground hidden md:block">{filename}</span>
        </div>
      </div>

      {/* Sandpack 容器 */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <SandpackProvider
          template="react"
          theme={isDarkMode ? nightOwl : githubLight}
          files={{
            '/App.js': wrappedCode,
            '/styles.css': TAILWIND_CSS,
            '/tailwind.config.js': {
              code: TAILWIND_CONFIG,
              hidden: true,
            },
          }}
          options={{
            recompileMode: 'delayed',
            recompileDelay: 500,
            autorun: true,
            autoReload: true,
            externalResources: ['https://cdn.tailwindcss.com'],
          }}
          customSetup={{
            dependencies: allDependencies,
          }}
        >
          {artifactId && <SandpackCodeListener artifactId={artifactId} originalCode={code} />}
          <SandpackStack className="flex-1">
            <SandpackLayout className={cn('flex-1 !rounded-none !border-0', showConsole && 'max-h-[calc(100%-140px)]')}>
              {viewMode === 'preview' && (
                <SandpackErrorBoundary labels={errorLabels}>
                  <SandpackPreview
                    showNavigator={false}
                    showRefreshButton={true}
                    showOpenInCodeSandbox={false}
                    className="h-full"
                  />
                </SandpackErrorBoundary>
              )}

              {viewMode === 'code' && (
                <SandpackCodeEditor
                  showTabs={false}
                  showLineNumbers={true}
                  showInlineErrors={true}
                  wrapContent={true}
                  readOnly={isGenerating}
                  className="h-full"
                />
              )}

              {viewMode === 'split' && (
                <>
                  <SandpackCodeEditor
                    showTabs={false}
                    showLineNumbers={true}
                    showInlineErrors={true}
                    wrapContent={true}
                    readOnly={isGenerating}
                    className="h-full"
                  />
                  <SandpackErrorBoundary labels={errorLabels}>
                    <SandpackPreview
                      showNavigator={false}
                      showRefreshButton={true}
                      showOpenInCodeSandbox={false}
                      className="h-full"
                    />
                  </SandpackErrorBoundary>
                </>
              )}
            </SandpackLayout>

            {/* 控制台面板 */}
            <ConsolePanel
              isOpen={showConsole}
              onToggle={toggleConsole}
              onClose={closeConsole}
              label={t('reactPreview.console')}
            />
          </SandpackStack>
        </SandpackProvider>
      </div>
    </div>
  );
});

ReactPreview.displayName = 'ReactPreview';

export default ReactPreview;
