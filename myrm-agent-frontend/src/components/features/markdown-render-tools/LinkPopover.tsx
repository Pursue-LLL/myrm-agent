'use client';

/* eslint-disable @next/next/no-img-element */
import React, { useState, useCallback, useEffect } from 'react';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/primitives/hover-card';
import { isTouchDevice as checkTouchDevice } from '@/lib/utils/deviceUtils';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';

export function formatRelativeDate(dateStr: string, t: (key: string, values?: Record<string, number>) => string): string {
  const parsed = new Date(dateStr);
  if (isNaN(parsed.getTime())) {return dateStr;}
  const now = Date.now();
  const diffMs = now - parsed.getTime();
  if (diffMs < 0) {return dateStr;}
  const diffDays = Math.floor(diffMs / 86_400_000);
  if (diffDays === 0) {return t('relativeDate.today');}
  if (diffDays === 1) {return t('relativeDate.yesterday');}
  if (diffDays < 7) {return t('relativeDate.daysAgo', { count: diffDays });}
  if (diffDays < 30) {return t('relativeDate.weeksAgo', { count: Math.floor(diffDays / 7) });}
  if (diffDays < 365) {return t('relativeDate.monthsAgo', { count: Math.floor(diffDays / 30) });}
  const y = parsed.getFullYear();
  const m = String(parsed.getMonth() + 1).padStart(2, '0');
  const d = String(parsed.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

interface LinkPopoverProps {
  url: string;
  title?: string;
  description?: string;
  label?: string;
  className?: string;
  children?: React.ReactNode;
  siteName?: string;
  authority?: string;
  date?: string;
}

const LinkPopover: React.FC<LinkPopoverProps> = React.memo(
  ({ url, title, description, label, className, children, siteName, authority, date }) => {
    const t = useTranslations('common');
    const [isTouch, setIsTouch] = useState(false);
    const [isOpen, setIsOpen] = useState(false);

    useEffect(() => {
      const updateDeviceType = () => setIsTouch(checkTouchDevice());
      updateDeviceType();
      window.addEventListener('resize', updateDeviceType);
      return () => window.removeEventListener('resize', updateDeviceType);
    }, []);

    const getDomain = (url: string) => {
      try {
        if (url === '#' || !url) {return null;}
        return new URL(url).hostname.replace(/^www\./, '');
      } catch {
        return null;
      }
    };

    const domain = getDomain(url);
    const isValidUrl = url && url !== '#';
    const faviconUrl = `https://s2.googleusercontent.com/s2/favicons?domain_url=${url}`;

    const handlePopoverClick = useCallback(() => {
      if (isValidUrl) {
        window.open(url, '_blank', 'noopener,noreferrer');
      }
    }, [isValidUrl, url]);

    const handleAgentBrowse = useCallback(
      (e: React.MouseEvent) => {
        e.stopPropagation();
        if (!isValidUrl) {return;}
        useChatStore.getState().sendMessage(t('agentBrowsePrompt', { url }));
        useBrowserInspectorStore.getState().openPanel();
        setIsOpen(false);
      },
      [isValidUrl, url, t],
    );

    const handleTriggerClick = useCallback(
      (e: React.MouseEvent) => {
        if (isTouch) {
          e.preventDefault();
          setIsOpen(!isOpen);
        }
      },
      [isTouch, isOpen],
    );

    const linkClassName = `bg-secondary px-1 rounded ml-1 no-underline text-xs text-black/70 dark:text-white/70 relative hover:bg-[#2a7f8e] hover:text-white transition-colors duration-200 ${className || ''}`;

    const popoverContent = (
      <div className="flex flex-col flex-1 min-h-0 cursor-pointer select-none" onClick={handlePopoverClick}>
        {domain && (
          <div className="flex items-center space-x-2 pb-2 mb-2 border-b border-border/50">
            <div className="w-4 h-4 flex-shrink-0 rounded overflow-hidden bg-white border border-border/30 inline-block">
              <img src={faviconUrl} width={16} height={16} alt="favicon" className="object-contain" loading="lazy" />
            </div>
            <span className="truncate font-medium text-xs text-muted-foreground">{siteName || domain}</span>
            {authority && (
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium leading-none whitespace-nowrap ${
                  authority === '官方'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                    : authority === '媒体'
                      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                      : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                }`}
              >
                {authority}
              </span>
            )}
            {date && <span className="text-[10px] text-muted-foreground/70 whitespace-nowrap">{formatRelativeDate(date, t)}</span>}
          </div>
        )}

        {title && (
          <div className="mb-2">
            <h4 className="font-semibold text-foreground text-sm leading-tight">{title}</h4>
          </div>
        )}

        {description && (
          <div className="bg-muted/30 rounded-md p-2 mb-2">
            <div
              className="max-h-56 overflow-y-auto text-muted-foreground text-xs leading-relaxed font-normal overscroll-contain scrollbar-thin scrollbar-thumb-gray-400 scrollbar-track-transparent"
              onWheel={(e) => e.stopPropagation()}
            >
              {description}
            </div>
          </div>
        )}

        {isValidUrl && (
          <div className="flex items-center justify-between pt-1.5 border-t border-border/50">
            <div className="flex items-center gap-1 cursor-pointer hover:opacity-70 transition-opacity">
              <svg className="w-3 h-3 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>
              <span className="text-xs text-primary font-medium">{t('clickToVisitLink')}</span>
            </div>
            <div
              className="flex items-center gap-1 cursor-pointer hover:opacity-70 transition-opacity"
              onClick={handleAgentBrowse}
            >
              <svg className="w-3 h-3 text-chart-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-2.47 2.47a2.25 2.25 0 01-1.59.659H9.06a2.25 2.25 0 01-1.591-.659L5 14.5m14 0V17a2.25 2.25 0 01-2.25 2.25H7.25A2.25 2.25 0 015 17v-2.5"
                />
              </svg>
              <span className="text-xs text-chart-2 font-medium">{t('agentBrowse')}</span>
            </div>
          </div>
        )}
      </div>
    );

    const triggerContent =
      children ||
      (isValidUrl ? (
        <a
          href={isTouch ? undefined : url}
          target={isTouch ? undefined : '_blank'}
          rel={isTouch ? undefined : 'noopener noreferrer'}
          className={linkClassName}
          onClick={handleTriggerClick}
        >
          {label}
        </a>
      ) : (
        <span className={linkClassName} onClick={handleTriggerClick}>
          {label}
        </span>
      ));

    return (
      <HoverCard
        openDelay={isTouch ? 0 : 200}
        open={isTouch ? isOpen : undefined}
        onOpenChange={isTouch ? setIsOpen : undefined}
      >
        <HoverCardTrigger asChild>
          {children ? (
            <div className="inline-block cursor-pointer" onClick={handleTriggerClick}>
              {children}
            </div>
          ) : (
            triggerContent
          )}
        </HoverCardTrigger>
        <HoverCardContent className="w-80 max-w-[90vw] max-h-80 p-3 flex flex-col">{popoverContent}</HoverCardContent>
      </HoverCard>
    );
  },
);

LinkPopover.displayName = 'LinkPopover';

export default LinkPopover;
