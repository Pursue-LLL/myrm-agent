'use client';

/**
 * Interactive Single-File HTML Export & Share Link Modal Component.
 *
 * [INPUT] chatId: string, chatTitle?: string, isOpen: boolean, onClose: () => void
 * [OUTPUT] SessionExportShareModal: Dual-mode dialog for Standalone HTML compile & HMAC share links.
 * [POS] src/components/features/session-export/SessionExportShareModal.tsx
 */

import { memo, useState, useCallback, useEffect } from 'react';
import { Download, Share2, FileCode, X, Loader2, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { ExportHtmlOptions, RedactionScan, ShareLinkResponse } from './sessionExportTypes';
import { sessionExportService } from './sessionExportService';
import { SecretRedactionPreview } from './SecretRedactionPreview';
import { ShareLinkPanel } from './ShareLinkPanel';

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
  const [scan, setScan] = useState<RedactionScan>({ status: 'scanning' });
  const [actionError, setActionError] = useState<'export' | 'share' | null>(null);

  // Share Link State
  const [ttlDays, setTtlDays] = useState<number>(7);
  const [sharePassword, setSharePassword] = useState('');
  const [isGeneratingLink, setIsGeneratingLink] = useState(false);
  const [shareResult, setShareResult] = useState<ShareLinkResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Scan the stored conversation for credentials whenever the modal opens for a chat
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    let cancelled = false;
    void sessionExportService
      .previewRedaction(chatId)
      .then((summary) => {
        if (!cancelled) {
          setScan({ status: 'ready', summary });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setScan({ status: 'failed' });
        }
      });
    return () => {
      cancelled = true;
      setScan({ status: 'scanning' });
    };
  }, [isOpen, chatId]);

  const selectTab = useCallback((tab: 'html' | 'share') => {
    setActiveTab(tab);
    setActionError(null);
  }, []);

  const handleExportHtml = useCallback(async () => {
    setIsExporting(true);
    setActionError(null);
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
    } catch {
      setActionError('export');
    } finally {
      setIsExporting(false);
    }
  }, [chatId, includeThinking, includeToolCalls, enableRedaction, theme, onClose]);

  const handleGenerateShareLink = useCallback(async () => {
    setIsGeneratingLink(true);
    setActionError(null);
    try {
      const res = await sessionExportService.createShareLink(chatId, {
        ttl_seconds: ttlDays * 24 * 3600,
        password: sharePassword.trim() || null,
      });
      setShareResult(res);
    } catch {
      setActionError('share');
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
              <h3 className="font-semibold text-xs">{t('modalTitle')}</h3>
              <p className="text-[10px] text-muted-foreground truncate max-w-[280px]">{chatTitle || chatId}</p>
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
              selectTab('html');
            }}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all',
              activeTab === 'html'
                ? 'bg-card text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Download className="h-3.5 w-3.5 text-primary" />
            <span>{t('tabDownloadHtml')}</span>
          </button>

          <button
            type="button"
            data-testid="tab-share-link"
            onClick={() => {
              selectTab('share');
            }}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all',
              activeTab === 'share'
                ? 'bg-card text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Share2 className="h-3.5 w-3.5 text-sky-500" />
            <span>{t('tabShareLink')}</span>
          </button>
        </div>

        {/* Tab 1: HTML Export */}
        {activeTab === 'html' && (
          <div className="p-4 flex flex-col gap-3 max-h-[75vh] overflow-y-auto">
            {/* Options Checkboxes */}
            <div className="flex flex-col gap-2 p-3 rounded-xl border border-border/80 bg-muted/20 text-xs">
              <label className="flex items-center justify-between cursor-pointer">
                <span className="font-medium text-foreground">{t('includeThinking')}</span>
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
                <span className="font-medium text-foreground">{t('includeToolCalls')}</span>
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
                <span className="font-medium text-foreground">{t('themePreset')}</span>
                <select
                  value={theme}
                  onChange={(e) => {
                    setTheme(e.target.value as 'system' | 'light' | 'dark');
                  }}
                  className="px-2 py-0.5 rounded border border-border bg-background text-xs text-foreground focus:outline-none"
                >
                  <option value="system">{t('themeSystem')}</option>
                  <option value="light">{t('themeLight')}</option>
                  <option value="dark">{t('themeDark')}</option>
                </select>
              </div>
            </div>

            {/* Secret Redaction Preview */}
            <SecretRedactionPreview
              scan={scan}
              enableRedaction={enableRedaction}
              onToggleRedaction={setEnableRedaction}
            />

            <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/20 text-[11px] text-muted-foreground flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary flex-shrink-0" />
              <span>{t('zeroDepHint')}</span>
            </div>
          </div>
        )}

        {/* Tab 2: Share Link */}
        {activeTab === 'share' && (
          <ShareLinkPanel
            ttlDays={ttlDays}
            onTtlDaysChange={setTtlDays}
            password={sharePassword}
            onPasswordChange={setSharePassword}
            result={shareResult}
            copied={copied}
            onCopy={handleCopyLink}
          />
        )}

        {actionError && (
          <p
            role="alert"
            data-testid="session-export-error"
            className="mx-4 mb-3 px-3 py-2 rounded-lg border border-destructive/30 bg-destructive/10 text-xs text-destructive"
          >
            {actionError === 'export' ? t('exportFailed') : t('shareLinkFailed')}
          </p>
        )}

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border/80 bg-muted/20">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            {t('cancel')}
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
                  <span>{t('compiling')}</span>
                </>
              ) : (
                <>
                  <Download className="h-3.5 w-3.5" />
                  <span>{t('compileAndDownload')}</span>
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
                  <span>{t('generating')}</span>
                </>
              ) : (
                <>
                  <Share2 className="h-3.5 w-3.5" />
                  <span>{t('generateLink')}</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
