'use client';

import React, { useCallback, useState } from 'react';
import { Check, Copy, Maximize2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import type { Artifact, ArtifactType } from '@/store/chat/types';
import { HtmlPreview } from '@/components/features/artifacts/renderers/MediaPreview';
import { CODE_BLOCK_THEME, CODE_BLOCK_CONTAINER, CODE_BLOCK_TOOLBAR } from '@/lib/constants/codeblock-theme';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

/**
 * Inline HTML Widget — renders HTML/SVG code blocks as live previews
 * with a compact toolbar for copy and full-screen portal view.
 */
const InlineHtmlWidget: React.FC<{
  language: string;
  value: string;
}> = ({ language, value }) => {
  const t = useTranslations('codeBlock');
  const [copied, setCopied] = useState(false);
  const { addTab, updateTabContent, updateTabLoading } = useArtifactPortalStore();

  const handleCopy = useCallback(() => {
    writeToClipboard(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [value]);

  const handleOpenPortal = useCallback(() => {
    const tempArtifact: Artifact = {
      id: `inline-html-${Date.now()}`,
      filename: `widget.${language.toLowerCase()}`,
      type: 'html' as ArtifactType,
      content_type: language.toLowerCase() === 'svg' ? 'image/svg+xml' : 'text/html',
      size: value.length,
      preview_url: '',
      download_url: '',
    };

    addTab(tempArtifact);
    setTimeout(() => {
      updateTabContent(tempArtifact.id, value);
      updateTabLoading(tempArtifact.id, false);
    }, 0);
  }, [language, value, addTab, updateTabContent, updateTabLoading]);

  return (
    <div
      className={cn(
        'relative overflow-hidden',
        CODE_BLOCK_CONTAINER.margin,
        CODE_BLOCK_CONTAINER.rounded,
        CODE_BLOCK_CONTAINER.shadow,
        `border ${CODE_BLOCK_THEME.light.border} dark:${CODE_BLOCK_THEME.dark.border}`,
      )}
    >
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
        <span className="font-mono">{language}</span>

        <div className="flex items-center space-x-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={handleOpenPortal}
                className="p-1 rounded-full text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors duration-150"
                aria-label={t('preview')}
              >
                <Maximize2 size={14} />
              </button>
            </TooltipTrigger>
            <TooltipContent>{t('preview')}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={handleCopy}
                className={cn(
                  'p-1 rounded-full transition-colors duration-150',
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

      <HtmlPreview content={value} injectTheme autoHeight />
    </div>
  );
};

InlineHtmlWidget.displayName = 'InlineHtmlWidget';

export default InlineHtmlWidget;
