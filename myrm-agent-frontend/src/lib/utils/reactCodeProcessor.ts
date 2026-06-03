/**
 * React代码处理工具函数
 */

import { OPTIONAL_DEPENDENCIES } from '@/components/features/artifacts/constants/reactPreviewConstants';

/** 判断代码是否为有效的 React 组件 */
export function isValidReactCode(code: string): boolean {
  const hasReactImport = /import\s+.*from\s+['"]react['"]/.test(code);
  const hasJsx = /<[A-Z][a-zA-Z0-9]*|<[a-z]+\s/.test(code);
  const hasExport = /export\s+(default\s+)?/.test(code);

  return (hasReactImport || hasJsx) && (hasExport || hasJsx);
}

/** 提取代码中使用的 React hooks */
export function extractUsedHooks(code: string): string[] {
  const hooks = [
    'useState',
    'useEffect',
    'useCallback',
    'useMemo',
    'useRef',
    'useContext',
    'useReducer',
    'useLayoutEffect',
    'useImperativeHandle',
    'useDebugValue',
    'useDeferredValue',
    'useTransition',
    'useId',
    'useSyncExternalStore',
    'useInsertionEffect',
  ];
  return hooks.filter((hook) => code.includes(hook));
}

/** 检测代码中使用的可选依赖 */
export function detectOptionalDependencies(code: string): Record<string, string> {
  const detected: Record<string, string> = {};

  for (const [pkg, version] of Object.entries(OPTIONAL_DEPENDENCIES)) {
    // 检测 import 语句
    const importRegex = new RegExp(`from\\s+['"]${pkg.replace('/', '\\/')}['"]`);
    if (importRegex.test(code)) {
      detected[pkg] = version;
    }
  }

  return detected;
}

/** 移除代码中已有的 React 导入，并返回清理后的代码 */
export function removeReactImport(code: string): string {
  return code
    .replace(/import\s+React\s*,?\s*\{[^}]*\}\s*from\s+['"]react['"];?\s*/g, '')
    .replace(/import\s+React\s+from\s+['"]react['"];?\s*/g, '')
    .replace(/import\s+\*\s+as\s+React\s+from\s+['"]react['"];?\s*/g, '')
    .replace(/import\s+\{[^}]*\}\s+from\s+['"]react['"];?\s*/g, '')
    .trim();
}

/** 生成 React 导入语句 */
export function generateReactImport(code: string): string {
  const usedHooks = extractUsedHooks(code);
  if (usedHooks.length > 0) {
    return `import React, { ${usedHooks.join(', ')} } from 'react';`;
  }
  return `import React from 'react';`;
}

/** 包装代码为可渲染的 App 组件 */
export function wrapCodeAsApp(code: string, _filename: string): string {
  const reactImport = generateReactImport(code);

  // 添加标记以便后续提取原始代码
  const originalCodeMarker = `\n// --- BEGIN ORIGINAL CODE ---\n${code}\n// --- END ORIGINAL CODE ---\n`;

  // 如果代码已经是完整的 App 组件，直接使用
  if (code.includes('export default') && /function\s+App\s*\(/.test(code)) {
    return `${reactImport}\n${removeReactImport(code)}${originalCodeMarker}`;
  }

  const cleanCode = removeReactImport(code);

  // 提取组件名
  const componentNameMatch = cleanCode.match(/(?:function|const|class)\s+([A-Z][a-zA-Z0-9]*)/);
  const componentName = componentNameMatch?.[1] || 'Component';

  // 如果代码导出了默认组件，包装它
  if (cleanCode.includes('export default')) {
    const codeWithoutExport = cleanCode.replace(/export\s+default\s+/, '');
    return `
${reactImport}
${codeWithoutExport}

export default function App() {
  return <${componentName} />;
}
${originalCodeMarker}`.trim();
  }

  // 如果代码是一个简单的组件定义（有 export 但不是 default）
  if (cleanCode.includes('export ')) {
    const codeWithoutExport = cleanCode.replace(/export\s+/g, '');
    return `
${reactImport}
${codeWithoutExport}

export default function App() {
  return <${componentName} />;
}
${originalCodeMarker}`.trim();
  }

  // 如果代码是一个简单的组件定义（无 export）
  if (/(?:function|const|class)\s+[A-Z]/.test(cleanCode)) {
    return `
${reactImport}
${cleanCode}

export default function App() {
  return <${componentName} />;
}
${originalCodeMarker}`.trim();
  }

  // 默认：假设代码是 JSX 片段，包装为 App
  return `
${reactImport}

export default function App() {
  return (
    <div className="p-4">
      ${cleanCode}
    </div>
  );
}
${originalCodeMarker}`.trim();
}
