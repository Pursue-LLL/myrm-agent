/**
 * [INPUT]
 * - reactCodeProcessor (POS: React 代码验证、包装、依赖检测工具)
 * - reactPreviewConstants (POS: Sandpack 预设依赖常量)
 *
 * [OUTPUT]
 * - useReactPreview: React 预览核心逻辑 Hook（代码验证、包装、依赖检测、错误文案）。
 *
 * [POS]
 * React 预览 Hook。为 ReactPreview 组件提供纯计算逻辑，无 UI 状态。
 */

import { useMemo } from 'react';
import { isValidReactCode, wrapCodeAsApp, detectOptionalDependencies } from '@/lib/utils/reactCodeProcessor';
import { PRESET_DEPENDENCIES } from '@/components/features/artifacts/constants/reactPreviewConstants';

interface UseReactPreviewParams {
  code: string;
  filename: string;
  t: (key: string) => string;
}

export function useReactPreview({ code, filename, t }: UseReactPreviewParams) {
  const errorLabels = useMemo(
    () => ({
      renderError: t('reactPreview.renderError'),
      renderErrorHint: t('reactPreview.renderErrorHint'),
      retry: t('reactPreview.retry'),
    }),
    [t],
  );

  const isValid = useMemo(() => isValidReactCode(code), [code]);

  const wrappedCode = useMemo(() => {
    if (!isValid) return code;
    return wrapCodeAsApp(code, filename);
  }, [code, filename, isValid]);

  const allDependencies = useMemo(() => {
    const optionalDeps = detectOptionalDependencies(code);
    return { ...PRESET_DEPENDENCIES, ...optionalDeps };
  }, [code]);

  return {
    isValid,
    wrappedCode,
    allDependencies,
    errorLabels,
  };
}
