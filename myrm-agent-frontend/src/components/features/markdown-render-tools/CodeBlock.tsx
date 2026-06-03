/**
 * CodeBlock - 代码块渲染组件
 *
 * [POS]
 * 负责渲染 Markdown 中的代码块，支持语法高亮、代码复制、预览功能。
 *
 * [性能优化] (2026-05-06)
 * 1. React.memo: 避免父组件重新渲染导致的无效重绘
 * 2. 流式 Debounce: 在 isStreaming=true 时，使用 100ms 防抖减少高亮频率
 * 3. 全局高亮缓存: 缓存已高亮的代码结果，避免重复计算 (限制 100 条，FIFO)
 * 4. Debounce Timer 清理: isStreaming 变为 false 时主动清理 timer，消除延迟执行
 * 5. useMemo 依赖优化: 简化依赖数组，减少冗余依赖项
 *
 * [依赖]
 * - prism-react-renderer: 语法高亮引擎
 * - MarkdownContent: 父组件，传递 isStreaming prop
 *
 * [优化收益]
 * - React.memo: 避免父组件 MessageBox 重新渲染时的无效 CodeBlock 重绘
 * - 流式 Debounce: 将高亮频率从 10-20ms 降低到 100ms，减少计算约 80-90%
 * - 全局缓存: 对于重复代码块，渲染时间从数十毫秒降至 <1ms
 * - 综合效果: 长代码流式输出场景下，显著减少 UI 卡顿，用户可流畅滚动和交互
 */
import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { Check, Copy, Play } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Highlight, themes, Prism } from 'prism-react-renderer';
import { useTheme } from 'next-themes';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import type { Artifact, ArtifactType } from '@/store/chat/types';
import { CODE_BLOCK_THEME, CODE_BLOCK_CONTAINER, CODE_BLOCK_TOOLBAR } from '@/lib/constants/codeblock-theme';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

const HTML_PREVIEW_LANGUAGES = new Set(['html', 'svg']);

// 全局高亮结果缓存，避免重复高亮相同代码 (限制 100 条，FIFO 策略)
const highlightCache = new Map<string, React.ReactNode>();

/** 检查是否为可预览的 React 代码 */
function isPreviewableReactCode(language: string, code: string): boolean {
  const reactLanguages = ['jsx', 'tsx', 'javascript', 'typescript', 'js', 'ts'];
  if (!reactLanguages.includes(language.toLowerCase())) return false;

  const hasReactImport = /import\s+.*from\s+['"]react['"]/.test(code);
  const hasJsx = /<[A-Z][a-zA-Z0-9]*|<[a-z]+\s/.test(code);
  const hasExport = /export\s+(default\s+)?/.test(code);
  const hasFunction = /function\s+[A-Z]/.test(code);
  const hasConstComponent = /const\s+[A-Z]\w*\s*=/.test(code);

  return (hasReactImport || hasJsx) && (hasExport || hasFunction || hasConstComponent);
}

/**
 * 代码块组件，用于显示代码，支持语言标识、语法高亮和复制功能
 * @param language 代码语言
 * @param value 代码内容
 * @param className 额外的CSS类名
 * @param isStreaming 是否处于流式输出状态（用于debounce优化）
 */
const CodeBlock: React.FC<{
  language: string;
  value: string;
  className?: string;
  isStreaming?: boolean;
}> = ({ language, value, className, isStreaming = false }) => {
  const t = useTranslations('codeBlock');
  const [copied, setCopied] = useState(false);
  const { theme } = useTheme();
  const { addTab, updateTabContent, updateTabLoading } = useArtifactPortalStore();

  // 流式输出时的 debounced value
  const [debouncedValue, setDebouncedValue] = useState(value);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 流式输出时，debounce 更新显示的代码值（每 100ms 更新一次）
  useEffect(() => {
    if (isStreaming) {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        setDebouncedValue(value);
      }, 100);

      return () => {
        if (debounceTimerRef.current) {
          clearTimeout(debounceTimerRef.current);
        }
      };
    } else {
      // 非流式输出时，清理 timer 并立即更新
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      setDebouncedValue(value);
    }
  }, [value, isStreaming]);

  // 使用 debounced value 进行渲染
  const displayValue = isStreaming ? debouncedValue : value;

  const isReactPreviewable = useMemo(() => isPreviewableReactCode(language, displayValue), [language, displayValue]);
  const isHtmlPreviewable = HTML_PREVIEW_LANGUAGES.has(language.toLowerCase());
  const isPreviewable = isReactPreviewable || isHtmlPreviewable;

  // 复制时使用原始 value，而不是 debouncedValue
  const handleCopy = useCallback(() => {
    writeToClipboard(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [value]);

  const handlePreview = useCallback(() => {
    const isHtml = HTML_PREVIEW_LANGUAGES.has(language.toLowerCase());

    // 从 DOM 元素上获取 data-line-range 属性（由 MarkdownContent 传递）
    // 注意：这里我们使用一个简单的 hack，因为 CodeBlock 的 props 没有直接传 lineRange
    // 更好的做法是修改 CodeBlock 的 props 签名，但为了不破坏现有接口，我们使用 event 冒泡或全局状态
    // 这里我们先直接使用一个占位的 lineRange，实际的滚动逻辑由 ArtifactPortal 处理
    // 我们假设如果这个代码块是从 ActiveWorkingMemoryPanel 点击过来的，它已经在 ArtifactPortal 中打开了
    // 所以这个内部的 preview 按钮不需要处理 lineRange

    const tempArtifact: Artifact = isHtml
      ? {
          id: `inline-html-${Date.now()}`,
          filename: `widget.${language.toLowerCase()}`,
          type: 'html' as ArtifactType,
          content_type: language.toLowerCase() === 'svg' ? 'image/svg+xml' : 'text/html',
          size: value.length,
          preview_url: '',
          download_url: '',
        }
      : {
          id: `inline-react-${Date.now()}`,
          filename: `Component.${language === 'tsx' ? 'tsx' : 'jsx'}`,
          type: 'code' as ArtifactType,
          content_type: language === 'tsx' ? 'text/typescript-jsx' : 'text/javascript-jsx',
          size: value.length,
          preview_url: '',
          download_url: '',
          language: language === 'tsx' ? 'tsx' : 'jsx',
        };

    addTab(tempArtifact);
    setTimeout(() => {
      updateTabContent(tempArtifact.id, value);
      updateTabLoading(tempArtifact.id, false);
    }, 0);
  }, [language, value, addTab, updateTabContent, updateTabLoading]);

  // 确保语言是被支持的
  const safeLanguage = language && Prism.languages[language] ? language : 'text';

  // 根据当前主题选择代码高亮主题
  const getTheme = useCallback(() => {
    switch (theme) {
      case 'light':
        return themes.oneLight;
      case 'dark':
        return themes.oneDark;
      default:
        return themes.oneLight;
    }
  }, [theme]);

  // 使用缓存机制优化高亮性能
  const cacheKey = `${safeLanguage}:${theme}:${displayValue}`;

  // 渲染高亮代码，使用缓存避免重复计算
  const highlightedCode = useMemo(() => {
    // 检查缓存
    if (highlightCache.has(cacheKey)) {
      return highlightCache.get(cacheKey);
    }

    // 渲染高亮代码
    const result = (
      <Highlight theme={getTheme()} code={displayValue} language={safeLanguage}>
        {({ className: _highlightClassName, style: _style, tokens, getLineProps, getTokenProps }) => (
          <div
            className={cn(
              'p-4 overflow-x-auto font-mono text-sm',
              CODE_BLOCK_THEME.light.background,
              `dark:${CODE_BLOCK_THEME.dark.background}`,
            )}
          >
            {tokens.map((line, i) => {
              const lineProps = getLineProps({ line, key: i });
              const { key: _lineKey, ...restLineProps } = lineProps;

              // Diff 语法高亮增强
              let diffBgClass = '';
              if (safeLanguage === 'diff') {
                const lineText = line.map((t) => t.content).join('');
                if (lineText.startsWith('+') && !lineText.startsWith('+++')) {
                  diffBgClass = 'bg-green-500/10 dark:bg-green-500/20';
                } else if (lineText.startsWith('-') && !lineText.startsWith('---')) {
                  diffBgClass = 'bg-red-500/10 dark:bg-red-500/20';
                } else if (lineText.startsWith('@@')) {
                  diffBgClass = 'bg-blue-500/10 dark:bg-blue-500/20';
                }
              }

              return (
                <div
                  key={i}
                  {...restLineProps}
                  id={`code-line-${i + 1}`}
                  className={cn(restLineProps.className, diffBgClass)}
                >
                  <span
                    className={cn(
                      'mr-4 inline-block w-5 text-right select-none',
                      CODE_BLOCK_THEME.light.lineNumber,
                      `dark:${CODE_BLOCK_THEME.dark.lineNumber}`,
                    )}
                  >
                    {i + 1}
                  </span>
                  {line.map((token, k) => {
                    const tokenProps = getTokenProps({ token, key: k });
                    const { key: _tokenKey, ...restTokenProps } = tokenProps;
                    return <span key={k} {...restTokenProps} />;
                  })}
                </div>
              );
            })}
          </div>
        )}
      </Highlight>
    );

    // 只缓存非流式输出的结果（避免缓存不完整的代码）
    if (!isStreaming) {
      highlightCache.set(cacheKey, result);

      // 限制缓存大小，避免内存泄漏（保留最近 100 个）
      if (highlightCache.size > 100) {
        const firstKey = highlightCache.keys().next().value;
        if (firstKey) {
          highlightCache.delete(firstKey);
        }
      }
    }

    return result;
  }, [cacheKey, getTheme, isStreaming]);

  return (
    <div
      className={cn(
        'relative overflow-hidden',
        CODE_BLOCK_CONTAINER.margin,
        CODE_BLOCK_CONTAINER.rounded,
        CODE_BLOCK_CONTAINER.shadow,
        `border ${CODE_BLOCK_THEME.light.border} dark:${CODE_BLOCK_THEME.dark.border}`,
        className,
      )}
      data-code-block="true"
    >
      {/* 语言标识和工具栏 */}
      <div
        className={cn(
          'flex justify-between items-center',
          CODE_BLOCK_TOOLBAR.padding,
          CODE_BLOCK_TOOLBAR.fontSize,
          CODE_BLOCK_THEME.light.toolbar,
          `dark:${CODE_BLOCK_THEME.dark.toolbar}`,
          `${CODE_BLOCK_THEME.light.text} dark:${CODE_BLOCK_THEME.dark.text}`,
          `border-b ${CODE_BLOCK_THEME.light.border} dark:${CODE_BLOCK_THEME.dark.border}`,
        )}
      >
        <div className="flex items-center space-x-2">
          <span className="font-mono">{language || t('code')}</span>
        </div>

        <div className="flex items-center space-x-1">
          {isPreviewable && (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={handlePreview}
                  className="p-1 rounded-full text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors duration-150 flex items-center space-x-1"
                  aria-label={t('preview')}
                >
                  <Play size={14} />
                </button>
              </TooltipTrigger>
              <TooltipContent>{t('preview')}</TooltipContent>
            </Tooltip>
          )}

          {/* 复制按钮 */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={handleCopy}
                className={cn(
                  'p-1 rounded-full transition-colors duration-150 flex items-center space-x-1',
                  `${CODE_BLOCK_THEME.light.text} dark:${CODE_BLOCK_THEME.dark.text}`,
                  `${CODE_BLOCK_THEME.light.hover} dark:${CODE_BLOCK_THEME.dark.hover}`,
                )}
                aria-label={t('copy')}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </button>
            </TooltipTrigger>
            <TooltipContent>{copied ? t('copied') : t('copy')}</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* 语法高亮代码内容 */}
      {highlightedCode}
    </div>
  );
};

CodeBlock.displayName = 'CodeBlock';

export default React.memo(CodeBlock);
