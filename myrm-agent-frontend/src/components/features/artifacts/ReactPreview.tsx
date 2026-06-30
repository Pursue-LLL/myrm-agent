'use client';

/**
 * [INPUT]
 * - @codesandbox/sandpack-react (POS: 浏览器端 React 代码沙箱渲染)
 * - useReactPreview (POS: React 预览核心逻辑：代码验证、包装、依赖检测)
 * - SandpackErrorBoundary (POS: Sandpack 编译/运行时错误边界)
 * - reactPreviewConstants (POS: Tailwind CSS/Config 预设常量)
 *
 * [OUTPUT]
 * - ReactPreview: React 组件纯预览器，将 JSX/TSX 代码渲染为可交互预览。
 *
 * [POS]
 * React 组件预览器。仅负责渲染预览，视图切换由 ArtifactPortal 的 PortalHeader 统一控制。
 */

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  SandpackProvider,
  SandpackPreview,
  SandpackLayout,
  SandpackStack,
} from '@codesandbox/sandpack-react';
import { nightOwl, githubLight } from '@codesandbox/sandpack-themes';
import { Code } from 'lucide-react';
import { TAILWIND_CSS, TAILWIND_CONFIG } from './constants/reactPreviewConstants';
import { SandpackErrorBoundary } from './components/SandpackErrorBoundary';
import { useReactPreview } from '@/hooks/useReactPreview';

interface ReactPreviewProps {
  code: string;
  filename: string;
  isDarkMode?: boolean;
}
const ReactPreview = memo<ReactPreviewProps>(({ code, filename, isDarkMode = false }) => {
  const t = useTranslations('artifacts');

  const {
    isValid,
    wrappedCode,
    allDependencies,
    errorLabels,
  } = useReactPreview({ code, filename, t });

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
    <div className="h-full overflow-hidden flex flex-col bg-background">
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
        <SandpackStack className="flex-1">
          <SandpackLayout className="flex-1 !rounded-none !border-0">
            <SandpackErrorBoundary labels={errorLabels}>
              <SandpackPreview
                showNavigator={false}
                showRefreshButton={true}
                showOpenInCodeSandbox={false}
                className="h-full"
              />
            </SandpackErrorBoundary>
          </SandpackLayout>
        </SandpackStack>
      </SandpackProvider>
    </div>
  );
});

ReactPreview.displayName = 'ReactPreview';

export default ReactPreview;
