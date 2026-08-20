'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { cn } from '@/lib/utils/classnameUtils';
import { ApiError } from '@/lib/api';
import { pushWeChatOfficialDraft, type WeChatComplianceHit } from '@/services/channels';
import { toast } from 'sonner';
import { useWechatCoverSuggest } from './useWechatCoverSuggest';
import { extractFirstLocalImageSrc } from './wechatDraftCoverUtils';
import {
  clampWechatAuthor,
  clampWechatDigest,
  normalizeWeChatComplianceHits,
  parseWeChatComplianceHits,
  resolveDefaultWechatAuthor,
  resolveDefaultWechatDraftTitle,
  type WeChatComplianceSeverity,
} from './wechatDraftPanelUtils';

export interface WeChatDraftPanelProps {
  artifactId: string;
  filename: string;
  htmlPath: string;
  chatId: string | null;
  agentName?: string | null;
  presetName?: string | null;
  fetchInlineContent: () => Promise<string | null>;
  onComplete?: () => void;
}

export function WeChatDraftPanel({
  artifactId,
  filename,
  htmlPath,
  chatId,
  agentName,
  presetName,
  fetchInlineContent,
  onComplete,
}: WeChatDraftPanelProps) {
  const t = useTranslations('artifacts.wechatDraft');
  const defaultTitle = useMemo(() => resolveDefaultWechatDraftTitle(filename), [filename]);
  const defaultAuthor = useMemo(() => resolveDefaultWechatAuthor(agentName, presetName), [agentName, presetName]);

  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [digest, setDigest] = useState('');
  const [coverPath, setCoverPath] = useState('');
  const [loading, setLoading] = useState(false);
  const [pushSucceeded, setPushSucceeded] = useState(false);
  const [complianceHits, setComplianceHits] = useState<WeChatComplianceHit[]>([]);
  const [complianceSeverity, setComplianceSeverity] = useState<WeChatComplianceSeverity | null>(null);

  const {
    suggestions: coverSuggestions,
    panelOpen: coverSuggestOpen,
    setPanelOpen: setCoverSuggestOpen,
    loading: coverSuggestLoading,
    selectSuggestion: selectCoverSuggestion,
  } = useWechatCoverSuggest({
    enabled: true,
    chatId,
    query: coverPath,
  });

  useEffect(() => {
    setTitle((prev) => (prev.trim() ? prev : defaultTitle));
  }, [defaultTitle]);

  useEffect(() => {
    setAuthor((prev) => (prev.trim() ? prev : defaultAuthor));
  }, [defaultAuthor]);

  useEffect(() => {
    if (coverPath.trim()) {
      return;
    }
    let cancelled = false;
    void (async () => {
      const html = await fetchInlineContent();
      if (cancelled || !html) {
        return;
      }
      const suggestedCover = extractFirstLocalImageSrc(html);
      if (suggestedCover) {
        setCoverPath((prev) => (prev.trim() ? prev : suggestedCover));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [coverPath, fetchInlineContent]);

  const handleSelectCoverSuggestion = useCallback((relativePath: string) => {
    setCoverPath(relativePath);
  }, []);

  const handlePush = useCallback(async () => {
    const resolvedTitle = title.trim() || defaultTitle;
    if (!resolvedTitle) {
      toast.error(t('titlePlaceholder'));
      return;
    }
    const resolvedAuthor = clampWechatAuthor(author);
    if (!resolvedAuthor) {
      toast.error(t('authorRequired'));
      return;
    }

    setLoading(true);
    setPushSucceeded(false);
    setComplianceHits([]);
    setComplianceSeverity(null);
    try {
      const payload: Parameters<typeof pushWeChatOfficialDraft>[0] = {
        htmlPath,
        title: resolvedTitle,
        author: resolvedAuthor,
      };
      const resolvedDigest = clampWechatDigest(digest);
      if (resolvedDigest) {
        payload.digest = resolvedDigest;
      }
      const trimmedCover = coverPath.trim();
      if (trimmedCover) {
        payload.coverPath = trimmedCover;
      }
      const result = await pushWeChatOfficialDraft(payload);
      const warnings = normalizeWeChatComplianceHits(result.complianceWarnings);
      toast.success(t('success'));
      if (result.manageUrl) {
        window.open(result.manageUrl, '_blank', 'noopener,noreferrer');
      }
      if (warnings.length > 0) {
        setComplianceHits(warnings);
        setComplianceSeverity('warning');
        setPushSucceeded(true);
        return;
      }
      setPushSucceeded(false);
      setComplianceHits([]);
      setComplianceSeverity(null);
      onComplete?.();
    } catch (error) {
      if (error instanceof ApiError && error.businessCode === 'wechat_compliance_blocked') {
        const hits = parseWeChatComplianceHits(error.data);
        setComplianceHits(hits);
        setComplianceSeverity('blocked');
        toast.error(error.message || t('complianceBlocked'), { duration: 6000 });
        return;
      }
      const message = error instanceof Error ? error.message : t('failed');
      if (message.toLowerCase().includes('credentials not configured')) {
        toast.error(t('credentialsMissing'));
      } else {
        toast.error(message || t('failed'));
      }
    } finally {
      setLoading(false);
    }
  }, [author, coverPath, defaultTitle, digest, htmlPath, onComplete, t, title]);

  const resolvedAuthorForGate = clampWechatAuthor(author) || clampWechatAuthor(defaultAuthor);
  const canConfirmPush = pushSucceeded || resolvedAuthorForGate.length > 0;

  return (
    <div
      className="mx-3 mb-3 rounded-lg border border-border/60 bg-muted/20 p-3 space-y-3"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor={`wechat-draft-title-${artifactId}`} className="text-xs">
            {t('titleLabel')}
          </Label>
          <Input
            id={`wechat-draft-title-${artifactId}`}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('titlePlaceholder')}
            className="h-8 text-sm"
            maxLength={64}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`wechat-draft-author-${artifactId}`} className="text-xs">
            {t('authorLabel')}
          </Label>
          <Input
            id={`wechat-draft-author-${artifactId}`}
            value={author}
            onChange={(e) => setAuthor(clampWechatAuthor(e.target.value))}
            placeholder={t('authorPlaceholder')}
            className="h-8 text-sm"
            maxLength={8}
            data-testid="wechat-draft-author-input"
          />
          <p className="text-[11px] text-muted-foreground leading-snug">{t('authorHint')}</p>
        </div>
        <div className="space-y-2">
          <Label htmlFor={`wechat-draft-digest-${artifactId}`} className="text-xs">
            {t('digestLabel')}
          </Label>
          <Input
            id={`wechat-draft-digest-${artifactId}`}
            value={digest}
            onChange={(e) => setDigest(clampWechatDigest(e.target.value))}
            placeholder={t('digestPlaceholder')}
            className="h-8 text-sm"
            maxLength={120}
            data-testid="wechat-draft-digest-input"
          />
          <p className="text-[11px] text-muted-foreground leading-snug">{t('digestHint')}</p>
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor={`wechat-draft-cover-${artifactId}`} className="text-xs">
          {t('coverLabel')}
        </Label>
        <div className="space-y-1">
          <Input
            id={`wechat-draft-cover-${artifactId}`}
            value={coverPath}
            onChange={(e) => {
              setCoverPath(e.target.value);
              setCoverSuggestOpen(true);
            }}
            onFocus={() => {
              if (chatId) {
                setCoverSuggestOpen(true);
              }
            }}
            placeholder={t('coverPlaceholder')}
            className="h-8 text-sm"
            autoComplete="off"
          />
          {chatId && coverSuggestOpen && (
            <div className="overflow-hidden rounded-md border border-border/60 bg-popover/95 shadow-sm">
              {coverSuggestLoading ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">{t('coverSuggestLoading')}</p>
              ) : coverSuggestions.length === 0 ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">{t('coverSuggestEmpty')}</p>
              ) : (
                <ul className="max-h-36 overflow-y-auto py-1">
                  {coverSuggestions.map((item) => (
                    <li key={`${item.reference_type}:${item.relative_path ?? item.file_id ?? item.label}`}>
                      <button
                        type="button"
                        className="flex w-full flex-col items-start px-3 py-1.5 text-left text-xs transition-colors hover:bg-accent/60"
                        onClick={() => {
                          const path = selectCoverSuggestion(item);
                          if (path) {
                            handleSelectCoverSuggestion(path);
                          }
                        }}
                      >
                        <span className="w-full truncate font-medium">{item.basename}</span>
                        <span className="w-full truncate text-muted-foreground">{item.relative_path}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground leading-snug">{t('coverHint')}</p>
      </div>
      {complianceHits.length > 0 && (
        <div
          data-testid="wechat-draft-compliance-panel"
          className={cn(
            'rounded-md border p-3 space-y-2',
            complianceSeverity === 'warning'
              ? 'border-amber-500/30 bg-amber-500/5'
              : 'border-destructive/30 bg-destructive/5',
          )}
        >
          <p
            className={cn(
              'text-xs font-medium',
              complianceSeverity === 'warning' ? 'text-amber-700 dark:text-amber-400' : 'text-destructive',
            )}
          >
            {complianceSeverity === 'warning' ? t('complianceSuccessTitle') : t('complianceTitle')}
          </p>
          <p className="text-[11px] text-muted-foreground leading-snug">
            {complianceSeverity === 'warning' ? t('complianceSuccessHint') : t('complianceHint')}
          </p>
          <ul className="space-y-2">
            {complianceHits.map((hit) => (
              <li key={hit.category} className="text-xs leading-snug">
                <span className="font-medium text-foreground">{hit.label}</span>
                <span className="ml-2 text-[11px] text-muted-foreground">
                  {hit.highRisk ? t('complianceHighRisk') : t('complianceWarning')}
                </span>
                <p className="mt-1 text-muted-foreground break-words">{hit.terms.join(' · ')}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Button
        size="sm"
        className="h-8 w-full sm:w-auto"
        variant={pushSucceeded ? 'outline' : 'default'}
        disabled={loading || !canConfirmPush}
        data-testid="wechat-draft-confirm-push"
        onClick={() => {
          if (pushSucceeded) {
            setPushSucceeded(false);
            setComplianceHits([]);
            setComplianceSeverity(null);
            return;
          }
          void handlePush();
        }}
      >
        {loading ? t('pushing') : pushSucceeded ? t('dismiss') : t('confirm')}
      </Button>
    </div>
  );
}
