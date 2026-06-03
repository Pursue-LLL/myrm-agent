'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Link as LinkIcon, Loader2, AlertCircle } from 'lucide-react';
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
import { toast } from '@/hooks/useToast';
import { analyzeDiscoveryUrl, installDiscoverySkillFromUrl, SkillUrlInfo } from '@/services/skill';

interface SkillUrlImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInstalled?: () => void;
  initialUrl?: string;
}

const SkillUrlImportDialog = memo(({ open, onOpenChange, onInstalled, initialUrl }: SkillUrlImportDialogProps) => {
  const t = useTranslations('settings.skills.discover');
  const [url, setUrl] = useState(initialUrl || '');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzedUrls, setAnalyzedUrls] = useState<SkillUrlInfo[]>([]);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());
  const [isInstalling, setIsInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset state when dialog opens/closes
  useEffect(() => {
    if (open) {
      setUrl(initialUrl || '');
      setAnalyzedUrls([]);
      setSelectedUrls(new Set());
      setError(null);

      // If we have an initial URL, automatically trigger analysis
      if (initialUrl && initialUrl.trim() !== '') {
        // Need to use a timeout to ensure the state is set before analyzing
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
      if (!targetUrl.trim()) return;
      setIsAnalyzing(true);
      setError(null);
      try {
        const res = await analyzeDiscoveryUrl(targetUrl.trim());
        if (res.urls && res.urls.length > 0) {
          setAnalyzedUrls(res.urls);
          // Default select all NOT installed
          const notInstalled = res.urls.filter((u) => !u.is_installed).map((u) => u.url);
          setSelectedUrls(new Set(notInstalled));

          if (res.urls.length === 1 && !res.urls[0].is_installed) {
            await handleInstallList([res.urls[0].url]);
          }
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
              const res = await installDiscoverySkillFromUrl(targetUrl);
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
    if (urlsToInstall.length === 0) return;
    handleInstallList(urlsToInstall);
  }, [selectedUrls]);

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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LinkIcon className="h-5 w-5 text-primary" />
            {t('importUrl')}
          </DialogTitle>
          <DialogDescription>{t('importUrlPlaceholder')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="flex items-center gap-2">
            <Input
              placeholder="https://github.com/..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAnalyze();
                }
              }}
              disabled={isAnalyzing || isInstalling || analyzedUrls.length > 1}
              className="flex-1"
            />
            {analyzedUrls.length <= 1 && (
              <Button onClick={() => void handleAnalyze()} disabled={!url.trim() || isAnalyzing || isInstalling}>
                {isAnalyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : t('import')}
              </Button>
            )}
          </div>

          {error && (
            <Alert variant="destructive" className="py-2">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          )}

          {analyzedUrls.length > 1 && (
            <div className="border rounded-full p-3 space-y-3 bg-muted/30">
              <p className="text-sm font-medium">{t('selectSkillsToImport')}</p>
              <div className="max-h-[200px] overflow-y-auto space-y-2 pr-2">
                {analyzedUrls.map((uInfo) => {
                  const u = uInfo.url;
                  const displayName = uInfo.name || u;
                  const isInstalled = uInfo.is_installed;

                  return (
                    <div
                      key={u}
                      className={`flex items-start space-x-2 p-2 rounded-full transition-colors ${isInstalled ? 'opacity-50 bg-muted/20' : 'hover:bg-muted/50'}`}
                    >
                      <Checkbox
                        id={`url-${u}`}
                        checked={selectedUrls.has(u)}
                        onCheckedChange={() => !isInstalled && toggleSelection(u)}
                        disabled={isInstalling || isInstalled}
                        className="mt-0.5"
                      />
                      <div className="grid gap-1.5 leading-none w-full">
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
          )}
        </div>

        {analyzedUrls.length > 1 && (
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isInstalling}>
              {t('cancel')}
            </Button>
            <Button onClick={handleImportSelected} disabled={selectedUrls.size === 0 || isInstalling}>
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
