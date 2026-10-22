'use client';

/**
 * Interactive Single-File HTML Export & Share Link Modal Component.
 *
 * [INPUT] chatId: string, chatTitle?: string, isOpen: boolean, onClose: () => void
 * [OUTPUT] SessionExportShareModal: Dual-mode dialog for Standalone HTML compile & HMAC share links.
 * [POS] src/components/features/session-export/SessionExportShareModal.tsx
 */

import { memo, useState, useCallback, useEffect } from 'react';
import {
  Download,
  Share2,
  FileCode,
  Check,
  Copy,
  X,
  Loader2,
  Lock,
  Calendar,
  Sparkles,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  ExportHtmlOptions,
  RedactionSummary,
  ShareLinkResponse,
} from './sessionExportTypes';
import { sessionExportService } from './sessionExportService';
import { SecretRedactionPreview } from './SecretRedactionPreview';

export interface SessionExportShareModalProps {
  chatId: string;
  chatTitle?: string;
  isOpen: boolean;
  onClose: () => void;
  className?: string;
}

export const SessionExportShareModal = memo(function SessionExportShareModal({
  chatId,
  chatTitle,
  isOpen,
  onClose,
  className,
}: SessionExportShareModalProps) {
  const t = useTranslations('sessionExport');

  const [activeTab, setActiveTab] = useState<'html' | 'share'>('html');

  // HTML Export State
  const [includeThinking, setIncludeThinking] = useState(true);
  const [includeToolCalls, setIncludeToolCalls] = useState(true);
  const [enableRedaction, setEnableRedaction] = useState(true);
  const [theme, setTheme] = useState<'system' | 'light' | 'dark'>('system');
  const [isExporting, setIsExporting] = useState(false);
  const [redactionSummary, setRedactionSummary] = useState<RedactionSummary | null>(null);

  // Share Link State
  const [ttlDays, setTtlDays] = useState<number>(7);
  const [sharePassword, setSharePassword] = useState('');
  const [isGeneratingLink, setIsGeneratingLink] = useState(false);
  const [shareResult, setShareResult] = useState<ShareLinkResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Initial secret detection preview on open
  useEffect(() => {
    if (isOpen && chatId) {
      void sessionExportService
        .previewRedaction(chatTitle || 'chat content sample sk-default')
        .then((sum) => {
          setRedactionSummary(sum);
        });
    }
  }, [isOpen, chatId, chatTitle]);

  const handleExportHtml = useCallback(async () => {
    setIsExporting(true);
    try {
      const options: ExportHtmlOptions = {
        include_thinking: includeThinking,
        include_tool_calls: includeToolCalls,
        enable_redaction: enableRedaction,
        theme,
      };
      const result = await sessionExportService.exportInteractiveHtml(chatId, options);
      sessionExportService.triggerDownload(result.file_name, result.html_content);
      onClose();
    } finally {
      setIsExporting(false);
    }
  }, [chatId, includeThinking, includeToolCalls, enableRedaction, theme, onClose]);

  const handleGenerateShareLink = useCallback(async () => {
    setIsGeneratingLink(true);
    try {
      const res = await sessionExportService.createShareLink(chatId, {
        ttl_seconds: ttlDays * 24 * 3600,
        password: sharePassword.trim() || null,
      });
      setShareResult(res);
    } finally {
      setIsGeneratingLink(false);
    }
  }, [chatId, ttlDays, sharePassword]);

  const handleCopyLink = useCallback(async () => {
    if (!shareResult) {
      return;
    }
    await navigator.clipboard.writeText(shareResult.share_url);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  }, [shareResult]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150 select-none"
      data-testid="session-export-share-modal"
    >
      <div
        className={cn(
          'w-full max-w-lg rounded-2xl border border-border bg-background shadow-2xl overflow-hidden flex flex-col text-foreground',
          className,
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/80 bg-muted/20">
          <div className="flex items-center gap-2">
            <div className="p-1 rounded-md bg-primary/10 text-primary">
              <FileCode className="h-4 w-4" />
            </div>
            <div>
              <h3 className="font-semibold text-xs">
                {t('modalTitle') || 'Session Export & Interactive Share Bridge'}
              </h3>
              <p className="text-[10px] text-muted-foreground truncate max-w-[280px]">
                {chatTitle || chatId}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-border/60 bg-muted/30 p-1">
          <button
            type="button"
            data-testid="tab-html-export"
            onClick={() => {
              setActiveTab('html');
            }}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all',
              activeTab === 'html'
                ? 'bg-card text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Download className="h-3.5 w-3.5 text-primary" />
            <span>{t('tabDownloadHtml') || 'Interactive HTML Bundle'}</span>
          </button>

          <button
            type="button"
            data-testid="tab-share-link"
            onClick={() => {
              setActiveTab('share');
            }}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all',
              activeTab === 'share'
                ? 'bg-card text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Share2 className="h-3.5 w-3.5 text-sky-500" />
            <span>{t('tabShareLink') || 'Read-Only Web Link'}</span>
          </button>
        </div>

        {/* Tab 1: HTML Export */}
        {activeTab === 'html' && (
          <div className="p-4 flex flex-col gap-3 max-h-[75vh] overflow-y-auto">
            {/* Options Checkboxes */}
            <div className="flex flex-col gap-2 p-3 rounded-xl border border-border/80 bg-muted/20 text-xs">
              <label className="flex items-center justify-between cursor-pointer">
                <span className="font-medium text-foreground">
                  {t('includeThinking') || 'Include Reasoning & Thinking Traces'}
                </span>
                <input
                  type="checkbox"
                  checked={includeThinking}
                  onChange={(e) => {
                    setIncludeThinking(e.target.checked);
                  }}
                  className="w-3.5 h-3.5 rounded border-border text-primary focus:ring-primary/40 cursor-pointer"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <span className="font-medium text-foreground">
                  {t('includeToolCalls') || 'Include Tool Call Inputs & Outputs'}
                </span>
                <input
                  type="checkbox"
                  checked={includeToolCalls}
                  onChange={(e) => {
                    setIncludeToolCalls(e.target.checked);
                  }}
                  className="w-3.5 h-3.5 rounded border-border text-primary focus:ring-primary/40 cursor-pointer"
                />
              </label>

              <div className="flex items-center justify-between pt-1 border-t border-border/40">
                <span className="font-medium text-foreground">
                  {t('themePreset') || 'Default HTML Theme'}
                </span>
                <select
                  value={theme}
                  onChange={(e) => {
                    setTheme(e.target.value as 'system' | 'light' | 'dark');
                  }}
                  className="px-2 py-0.5 rounded border border-border bg-background text-xs text-foreground focus:outline-none"
                >
                  <option value="system">{t('themeSystem') || 'System Auto'}</option>
                  <option value="light">{t('themeLight') || 'Light'}</option>
                  <option value="dark">{t('themeDark') || 'Dark'}</option>
                </select>
              </div>
            </div>

            {/* Secret Redaction Preview */}
            <SecretRedactionPreview
              redactionSummary={redactionSummary}
              enableRedaction={enableRedaction}
              onToggleRedaction={setEnableRedaction}
            />

            <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/20 text-[11px] text-muted-foreground flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary flex-shrink-0" />
              <span>
                {t('zeroDepHint') || 'Generated HTML is completely self-contained with inlined CSS & Vanilla JS. Opens offline in any browser.'}
              </span>
            </div>
          </div>
        )}

        {/* Tab 2: Share Link */}
        {activeTab === 'share' && (
          <div className="p-4 flex flex-col gap-3 max-h-[75vh] overflow-y-auto text-xs">
            <div className="flex flex-col gap-2 p-3 rounded-xl border border-border/80 bg-muted/20">
              <div className="flex items-center justify-between">
                <span className="font-medium text-foreground flex items-center gap-1">
                  <Calendar className="h-3.5 w-3.5 text-primary" />
                  <span>{t('linkExpiry') || 'Link Expiration Window'}</span>
                </span>
                <select
                  value={ttlDays}
                  onChange={(e) => {
                    setTtlDays(Number(e.target.value));
                  }}
                  className="px-2 py-0.5 rounded border border-border bg-background text-xs text-foreground focus:outline-none"
                >
                  <option value={7}>{t('expiry7Days') || '7 Days'}</option>
                  <option value={30}>{t('expiry30Days') || '30 Days'}</option>
                </select>
              </div>

              <div className="flex flex-col gap-1 pt-1 border-t border-border/40">
                <span className="font-medium text-foreground flex items-center gap-1">
                  <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                  <span>{t('optionalPassword') || 'Optional Passcode Protection'}</span>
                </span>
                <input
                  type="password"
                  value={sharePassword}
                  onChange={(e) => {
                    setSharePassword(e.target.value);
                  }}
                  placeholder={t('passwordPlaceholder') || 'Leave empty for public link...'}
                  className="w-full px-2.5 py-1 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary/50 text-foreground"
                />
              </div>
            </div>

            {/* Generated Share Link Result Card */}
            {shareResult && (
              <div className="flex flex-col gap-1.5 p-3 rounded-xl border border-primary/30 bg-primary/5">
                <span className="font-semibold text-[11px] text-primary">
                  {t('shareLinkReady') || 'Secure Share Link Ready'}
                </span>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={shareResult.share_url}
                    className="flex-1 px-2.5 py-1 text-xs rounded-lg border border-border bg-background font-mono text-foreground"
                    data-testid="share-url-input"
                  />
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs transition-all"
                    data-testid="copy-link-btn"
                  >
                    {copied ? (
                      <>
                        <Check className="h-3.5 w-3.5" />
                        <span>{t('copied') || 'Copied'}</span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5" />
                        <span>{t('copy') || 'Copy'}</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border/80 bg-muted/20">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            {t('cancel') || 'Cancel'}
          </button>

          {activeTab === 'html' ? (
            <button
              type="button"
              onClick={handleExportHtml}
              disabled={isExporting}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs transition-all"
              data-testid="compile-html-btn"
            >
              {isExporting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>{t('compiling') || 'Compiling...'}</span>
                </>
              ) : (
                <>
                  <Download className="h-3.5 w-3.5" />
                  <span>{t('compileAndDownload') || 'Compile & Download HTML'}</span>
                </>
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleGenerateShareLink}
              disabled={isGeneratingLink}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs transition-all"
              data-testid="generate-link-btn"
            >
              {isGeneratingLink ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>{t('generating') || 'Generating...'}</span>
                </>
              ) : (
                <>
                  <Share2 className="h-3.5 w-3.5" />
                  <span>{t('generateLink') || 'Generate Share Link'}</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
