'use client';

import React, { useState, useMemo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { Highlight, themes } from 'prism-react-renderer';
import { useTheme } from 'next-themes';
import { IconChevronDown, IconChevronUp, IconCopy, IconCheck } from '@/components/ui/icons/PremiumIcons';
import { motion, AnimatePresence } from 'framer-motion';
import { PremiumTooltip } from '@/components/ui/PremiumTooltip';

interface EnhancedSyntaxHighlighterProps {
  code: string;
  language?: string;
  maxCollapsedLines?: number;
  title?: string;
}

export const EnhancedSyntaxHighlighter: React.FC<EnhancedSyntaxHighlighterProps> = ({
  code,
  language = 'json',
  maxCollapsedLines = 2,
  title,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [renderFullContent, setRenderFullContent] = useState(false);
  const [copied, setCopied] = useState(false);
  const t = useTranslations('progressSteps');
  const { theme } = useTheme();

  const lines = useMemo(() => code.split('\n'), [code]);
  const isLongCode = lines.length > maxCollapsedLines;

  const displayedCode = isLongCode && !renderFullContent ? lines.slice(0, maxCollapsedLines).join('\n') : code;
  const hiddenLines = lines.length - maxCollapsedLines;

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await writeToClipboard(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const codeTheme = theme === 'dark' ? themes.oneDark : themes.oneLight;

  // 【性能高亮熔断机制】代码超过 50000 字符，降级为纯文本，彻底防冻结主线程
  const isTooLongToHighlight = code.length > 50000;
  const safeLanguage = isTooLongToHighlight ? 'text' : language;

  return (
    <div className="relative mt-2">
      <div
        className={cn(
          'relative rounded-xl overflow-hidden',
          'bg-zinc-50/50 dark:bg-zinc-900/50',
          'border border-zinc-200/80 dark:border-zinc-800/80',
          ' dark:shadow-none',
        )}
      >
        <div className="flex items-center justify-between px-3 py-2 bg-zinc-100/50 dark:bg-zinc-900/80 border-b border-zinc-200/80 dark:border-zinc-800/80">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 opacity-60 hover:opacity-100 transition-opacity">
              <div className="w-2.5 h-2.5 rounded-full bg-zinc-300 dark:bg-zinc-700" />
              <div className="w-2.5 h-2.5 rounded-full bg-zinc-300 dark:bg-zinc-700" />
              <div className="w-2.5 h-2.5 rounded-full bg-zinc-300 dark:bg-zinc-700" />
            </div>
            {title && (
              <span className="ml-1 text-[11px] font-medium text-zinc-500 dark:text-zinc-400 font-mono tracking-wide">
                {title}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            <PremiumTooltip tooltipContent={copied ? t('copied') || 'Copied!' : t('copy') || 'Copy'} side="top">
              <button
                onClick={handleCopy}
                className={cn(
                  'flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium',
                  'text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100',
                  'hover:bg-zinc-200/50 dark:hover:bg-zinc-800/50',
                  'transition-all duration-200',
                  copied && 'text-green-600 dark:text-green-400',
                )}
              >
                {copied ? <IconCheck className="w-3.5 h-3.5" /> : <IconCopy className="w-3.5 h-3.5" />}
              </button>
            </PremiumTooltip>

            {isLongCode && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (!isExpanded) {
                    setRenderFullContent(true);
                    setIsExpanded(true);
                  } else {
                    setIsExpanded(false);
                  }
                }}
                className={cn(
                  'flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium',
                  'text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100',
                  'hover:bg-zinc-200/50 dark:hover:bg-zinc-800/50',
                  'transition-all duration-200',
                )}
              >
                {isExpanded ? (
                  <>
                    <IconChevronUp className="w-3.5 h-3.5" />
                    <span>{t('collapse')}</span>
                  </>
                ) : (
                  <>
                    <IconChevronDown className="w-3.5 h-3.5" />
                    <span>+{hiddenLines}</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        <motion.div
          className="relative overflow-hidden group"
          initial={false}
          animate={{ height: isExpanded ? 'auto' : 72 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          onAnimationComplete={() => {
            if (!isExpanded) {
              setRenderFullContent(false);
            }
          }}
        >
          <Highlight theme={codeTheme} code={displayedCode} language={safeLanguage}>
            {({ className, style, tokens, getLineProps, getTokenProps }) => (
              <pre
                className={cn(
                  className,
                  'p-3 text-[13px] leading-relaxed font-mono',
                  'whitespace-pre-wrap break-words',
                  isExpanded
                    ? 'max-h-[500px] overflow-y-auto scrollbar-thin scrollbar-thumb-zinc-300 dark:scrollbar-thumb-zinc-700 scrollbar-track-transparent'
                    : 'overflow-hidden',
                )}
                style={{ ...style, backgroundColor: 'transparent' }}
              >
                <code className="text-zinc-800 dark:text-zinc-200">
                  {tokens.map((line, i) => {
                    const lineContent = line.map((t) => t.content).join('');
                    const leadingSpacesMatch = lineContent.match(/^ */);
                    const leadingSpaces = leadingSpacesMatch ? leadingSpacesMatch[0].length : 0;
                    const paddingLeft = leadingSpaces * 0.5; // rem

                    if (line.length === 1 && line[0].content === '' && i === tokens.length - 1) {
                      return null;
                    }

                    return (
                      <div key={i} {...getLineProps({ line, key: i })} className="flex w-full">
                        <span className="select-none w-8 text-right pr-4 text-zinc-400/50 dark:text-zinc-500/50 text-xs leading-relaxed flex-shrink-0">
                          {i + 1}
                        </span>
                        <span
                          className="flex-1"
                          style={{
                            paddingLeft: `${paddingLeft}rem`,
                            textIndent: `-${paddingLeft}rem`,
                            wordBreak: 'break-word',
                          }}
                        >
                          {line.map((token, key) => (
                            <span key={key} {...getTokenProps({ token, key })} />
                          ))}
                        </span>
                      </div>
                    );
                  })}
                </code>
              </pre>
            )}
          </Highlight>

          <AnimatePresence>
            {!isExpanded && isLongCode && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.9 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className={cn(
                  'absolute bottom-0 left-0 right-0 h-16 cursor-pointer',
                  'bg-gradient-to-t from-zinc-50 dark:from-zinc-900 to-transparent',
                  'hover:opacity-100',
                )}
                onClick={(e) => {
                  e.stopPropagation();
                  setIsExpanded(true);
                }}
              />
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </div>
  );
};
