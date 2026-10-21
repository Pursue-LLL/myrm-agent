'use client';

import React, { useMemo } from 'react';
import type { CodeItem } from '../utils';
import { EnhancedSyntaxHighlighter } from './EnhancedSyntaxHighlighter';

interface CodeRendererProps {
  items: CodeItem[];
  messageId: string;
  stepIndex: number;
}

/**
 * 代码内容渲染器
 * 用于展示 bash_code_execute_tool 执行的代码
 * 支持展开/收起功能和复制
 */
const CodeRenderer: React.FC<CodeRendererProps> = ({ items }) => {
  // 合并所有代码项
  const fullCode = useMemo(() => items.map((item) => item.code).join('\n'), [items]);

  return <EnhancedSyntaxHighlighter code={fullCode} language="bash" maxCollapsedLines={2} />;
};

export default CodeRenderer;
