/**
 * React预览Hook
 *
 * 管理React预览的状态和逻辑：视图模式、控制台、代码验证、依赖检测等
 *
 * @example
 * ```tsx
 * const {
 *   viewMode,
 *   setViewMode,
 *   showConsole,
 *   toggleConsole,
 *   closeConsole,
 *   isValid,
 *   wrappedCode,
 *   allDependencies,
 *   errorLabels
 * } = useReactPreview({ code, filename, t });
 * ```
 */

import { useState, useCallback, useMemo } from 'react';
import { isValidReactCode, wrapCodeAsApp, detectOptionalDependencies } from '@/lib/utils/reactCodeProcessor';
import { PRESET_DEPENDENCIES } from '@/components/features/artifacts/constants/reactPreviewConstants';

interface UseReactPreviewParams {
  code: string;
  filename: string;
  t: (key: string) => string;
}

export function useReactPreview({ code, filename, t }: UseReactPreviewParams) {
  const [viewMode, setViewMode] = useState<'preview' | 'code' | 'split'>('preview');
  const [showConsole, setShowConsole] = useState(false);

  // 错误边界文案
  const errorLabels = useMemo(
    () => ({
      renderError: t('reactPreview.renderError'),
      renderErrorHint: t('reactPreview.renderErrorHint'),
      retry: t('reactPreview.retry'),
    }),
    [t],
  );

  // 检查代码是否有效
  const isValid = useMemo(() => isValidReactCode(code), [code]);

  // 包装代码
  const wrappedCode = useMemo(() => {
    if (!isValid) return code;
    return wrapCodeAsApp(code, filename);
  }, [code, filename, isValid]);

  // 处理代码变更
  const _handleCodeChange = useCallback((_newCode: string) => {
    // SandpackCodeEditor onChange 会触发此回调
    // 但由于 Sandpack 的内部机制，我们需要通过 ActiveFile 监听
  }, []);

  // 检测并合并依赖
  const allDependencies = useMemo(() => {
    const optionalDeps = detectOptionalDependencies(code);
    return { ...PRESET_DEPENDENCIES, ...optionalDeps };
  }, [code]);

  // 控制台切换
  const toggleConsole = useCallback(() => setShowConsole((prev) => !prev), []);
  const closeConsole = useCallback(() => setShowConsole(false), []);

  return {
    viewMode,
    setViewMode,
    showConsole,
    toggleConsole,
    closeConsole,
    isValid,
    wrappedCode,
    allDependencies,
    errorLabels,
  };
}
