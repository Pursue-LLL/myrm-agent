'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Link as LinkIcon, Loader2, AlertCircle, ShieldAlert } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Checkbox } from '@/components/primitives/checkbox';
import { Alert, AlertDescription } from '@/components/primitives/alert';
import { toast } from '@/hooks/shared/useToast';
import { analyzeDiscoveryUrl, installDiscoverySkillFromUrl, SkillUrlInfo } from '@/services/skill';
import useChatStore from '@/store/useChatStore';
import { isLocalMode } from '@/lib/deploy-mode';

interface SkillUrlImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInstalled?: () => void;
  initialUrl?: string;
}

const SkillUrlImportDialog = memo(({ open, onOpenChange, onInstalled, initialUrl }: SkillUrlImportDialogProps) => {
  const t = useTranslations('settings.skills.discover');
  const mountAgentId = useChatStore((state) => state.agentConfig?.agentId) ?? 'builtin-general';
  const [url, setUrl] = useState(initialUrl || '');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzedUrls, setAnalyzedUrls] = useState<SkillUrlInfo[]>([]);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());
  const [isInstalling, setIsInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trustedSourceConfirmed, setTrustedSourceConfirmed] = useState(false);

  // Reset state when dialog opens/closes
  useEffect(() => {
    if (open) {
      setUrl(initialUrl || '');
      setAnalyzedUrls([]);
      setSelectedUrls(new Set());
      setError(null);
      setTrustedSourceConfirmed(false);

      if (initialUrl && initialUrl.trim() !== '') {
        setTimeout(() => {
          handleAnalyze(initialUrl);
        }, 100);
      }
    }
  }, [open, initialUrl]);

  const chunkArray = <T,>(arr: T[], size: number): T[][] =>
    Array.from({ length: Math.ceil(arr.length / size) }, (_, i) => arr.slice(i * size, i * size + size));

  const handleAnalyze = useCallback(
    async (urlToAnalyze?: string) => {
      const targetUrl = urlToAnalyze || url;
      if (!targetUrl.trim()) {
        return;
      }
      setIsAnalyzing(true);
      setError(null);
      setTrustedSourceConfirmed(false);
      try {
        const res = await analyzeDiscoveryUrl(targetUrl.trim());
        if (res.urls && res.urls.length > 0) {
          setAnalyzedUrls(res.urls);
          // Default select all NOT installed
          const notInstalled = res.urls.filter((u) => !u.is_installed).map((u) => u.url);
          setSelectedUrls(new Set(notInstalled));
        } else {
          setError(t('analyzeFailed') || 'No valid skills found at this URL');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t('analyzeFailed'));
      } finally {
        setIsAnalyzing(false);
      }
    },
    [url, t],
  );

  const handleInstallList = async (urlsToInstall: string[]) => {
    setIsInstalling(true);
    setError(null);
    let successCount = 0;
    try {
      const chunks = chunkArray(urlsToInstall, 3);
      for (const chunk of chunks) {
        const results = await Promise.all(
          chunk.map(async (targetUrl) => {
            try {
              const res = await installDiscoverySkillFromUrl(targetUrl, {
                agentId: mountAgentId,
                mountToAgent: true,
              });
              if (res.success) {
                return true;
              } else {
                toast({ title: res.error || t('installFailed'), variant: 'destructive' });
                return false;
              }
            } catch (err) {
              toast({ title: err instanceof Error ? err.message : t('installFailed'), variant: 'destructive' });
              return false;
            }
          }),
        );
        successCount += results.filter(Boolean).length;
      }

      if (successCount > 0) {
        toast({ title: t('installed') });
        onInstalled?.();
        onOpenChange(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('installFailed'));
    } finally {
      setIsInstalling(false);
    }
  };

  const handleImportSelected = useCallback(() => {
    const urlsToInstall = Array.from(selectedUrls);
    if (urlsToInstall.length === 0 || !trustedSourceConfirmed) {
      return;
    }
    handleInstallList(urlsToInstall);
  }, [selectedUrls, trustedSourceConfirmed]);

  const toggleSelection = (u: string) => {
    setSelectedUrls((prev) => {
      const next = new Set(prev);
      if (next.has(u)) {
        next.delete(u);
      } else {
        next.add(u);
      }
      return next;
    });
  };

  const handleUrlChange = (newUrl: string) => {
    setUrl(newUrl);
    if (analyzedUrls.length > 0) {
      setAnalyzedUrls([]);
      setSelectedUrls(new Set());
      setTrustedSourceConfirmed(false);
      setError(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LinkIcon className="h-5 w-5 text-primary" />
            {t('importUrl')}
          </DialogTitle>
          <DialogDescription>{t('importUrlPlaceholder')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-3">
          <div className="flex items-center gap-2">
            <Input
              data-testid="skill-url-input"
              placeholder="https://github.com/..."
              value={url}
              onChange={(e) => handleUrlChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAnalyze();
                }
              }}
              disabled={isAnalyzing || isInstalling}
              className="flex-1"
            />
            <Button
              data-testid="analyze-url-btn"
              onClick={() => void handleAnalyze()}
              disabled={!url.trim() || isAnalyzing || isInstalling}
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  {t('analyzingUrl')}
                </>
              ) : (
                t('import')
              )}
            </Button>
          </div>

          {error && (
            <Alert variant="destructive" className="py-2">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          )}

          {analyzedUrls.length > 0 && (
            <div className="space-y-3.5">
              <div
                className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-2 text-xs text-amber-900 dark:text-amber-200"
                data-testid="security-disclosure-card"
              >
                <div className="flex items-center gap-2 font-semibold text-amber-800 dark:text-amber-300">
                  <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0" />
                  <span>{t('securityDisclosureTitle')}</span>
                </div>
                <p className="text-muted-foreground leading-relaxed">
                  {isLocalMode() ? t('securityDisclosureLocal') : t('securityDisclosureCloud')}
                </p>
                <div className="flex items-start gap-2 pt-1 border-t border-amber-500/20">
                  <Checkbox
                    id="trusted-source-checkbox"
                    data-testid="trusted-source-checkbox"
                    checked={trustedSourceConfirmed}
                    onCheckedChange={(c) => setTrustedSourceConfirmed(!!c)}
                    disabled={isInstalling}
                    className="mt-0.5"
                  />
                  <label
                    htmlFor="trusted-source-checkbox"
                    className="text-xs font-medium text-foreground cursor-pointer leading-tight select-none"
                  >
                    {t('trustedSourceConfirm')}
                  </label>
                </div>
              </div>

              <div className="border rounded-lg p-3 space-y-2.5 bg-muted/30">
                <p className="text-sm font-medium">{t('selectSkillsToImport')}</p>
                <div className="max-h-[180px] overflow-y-auto space-y-2 pr-1">
                  {analyzedUrls.map((uInfo) => {
                    const u = uInfo.url;
                    const displayName = uInfo.name || u;
                    const isInstalled = uInfo.is_installed;

                    return (
                      <div
                        key={u}
                        data-testid={`skill-item-${displayName}`}
                        className={`flex items-start space-x-2 p-2 rounded-lg transition-colors ${
                          isInstalled ? 'opacity-50 bg-muted/20' : 'hover:bg-muted/50'
                        }`}
                      >
                        <Checkbox
                          id={`url-${u}`}
                          checked={selectedUrls.has(u)}
                          onCheckedChange={() => !isInstalled && toggleSelection(u)}
                          disabled={isInstalling || isInstalled}
                          className="mt-0.5"
                        />
                        <div className="grid gap-1 leading-none w-full">
                          <div className="flex items-center justify-between">
                            <label
                              htmlFor={`url-${u}`}
                              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                            >
                              {displayName}
                            </label>
                            {isInstalled && (
                              <span className="text-[10px] bg-secondary px-1.5 py-0.5 rounded text-secondary-foreground">
                                {t('alreadyInstalled')}
                              </span>
                            )}
                          </div>
                          {uInfo.description && (
                            <p className="text-xs text-muted-foreground line-clamp-1">{uInfo.description}</p>
                          )}
                          <p className="text-[10px] text-muted-foreground/60 break-all">{u}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {analyzedUrls.length > 0 && (
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isInstalling}>
              {t('cancel')}
            </Button>
            <Button
              data-testid="import-skills-btn"
              onClick={handleImportSelected}
              disabled={selectedUrls.size === 0 || isInstalling || !trustedSourceConfirmed}
            >
              {isInstalling ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('installing')}
                </>
              ) : (
                t('importSelected')
              )}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
});

SkillUrlImportDialog.displayName = 'SkillUrlImportDialog';
export default SkillUrlImportDialog;
