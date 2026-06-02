'use client';

import { memo, useState, useCallback } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  IconGlow,
  IconLoader,
  IconShieldAlert,
  IconShieldCheck,
  IconAlertTriangle,
  IconCheck,
  IconX,
} from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { fetchWithTimeout } from '@/lib/api';
import { toast } from '@/lib/utils/toast';
import type { SecurityConfigValue } from '@/services/config/types';

interface PolicyWarning {
  message: string;
  severity: 'info' | 'warning' | 'danger';
  field: string;
}

interface GenerateResult {
  generated_config: Record<string, unknown>;
  explanation_zh: string;
  explanation_en: string;
  warnings: PolicyWarning[];
  is_valid: boolean;
}

interface NLPolicyGeneratorProps {
  currentConfig: SecurityConfigValue | null;
  onApply: (config: Record<string, unknown>) => void;
}

const NLPolicyGenerator = memo(({ currentConfig, onApply }: NLPolicyGeneratorProps) => {
  const t = useTranslations('settings.securityPolicy.nlGenerator');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);

  const handleGenerate = useCallback(async () => {
    if (!input.trim() || loading) return;

    setLoading(true);
    setResult(null);

    try {
      const resp = await fetchWithTimeout(
        '/security/generate-policy',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: input.trim(),
            current_config: currentConfig
              ? {
                  permissions: currentConfig.permissions,
                  pathPolicy: currentConfig.pathPolicy,
                  networkAllowlist: currentConfig.networkAllowlist,
                }
              : null,
          }),
        },
        30000,
      );

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
        toast.error(err.detail || t('generateFailed'));
        return;
      }

      const data: GenerateResult = await resp.json();
      setResult(data);
    } catch {
      toast.error(t('generateFailed'));
    } finally {
      setLoading(false);
    }
  }, [input, loading, currentConfig, t]);

  const handleApply = useCallback(() => {
    if (!result) return;
    onApply(result.generated_config);
    setResult(null);
    setInput('');
    toast.success(t('applied'));
  }, [result, onApply, t]);

  const handleCancel = useCallback(() => {
    setResult(null);
  }, []);

  const locale = useLocale();

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <IconGlow className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium text-foreground">{t('title')}</span>
      </div>
      <p className="text-xs text-muted-foreground">{t('description')}</p>

      <div className="flex flex-col sm:flex-row gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t('placeholder')}
          className="min-h-[60px] max-h-[120px] text-sm resize-none flex-1"
          disabled={loading}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              handleGenerate();
            }
          }}
        />
        <Button
          onClick={handleGenerate}
          disabled={!input.trim() || loading}
          className="shrink-0 self-end sm:self-end"
          size="sm"
        >
          {loading ? <IconLoader className="h-4 w-4 animate-spin mr-1.5" /> : <IconGlow className="h-4 w-4 mr-1.5" />}
          {t('generate')}
        </Button>
      </div>

      {result && (
        <div className="rounded-lg border border-border bg-muted/30 p-3 sm:p-4 space-y-3 animate-in fade-in-0 slide-in-from-top-2 duration-200">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div className="flex items-center gap-2">
              {result.is_valid ? (
                <IconShieldCheck className="h-4 w-4 text-emerald-500" />
              ) : (
                <IconShieldAlert className="h-4 w-4 text-destructive" />
              )}
              <span className="text-sm font-medium">{result.is_valid ? t('resultValid') : t('resultDanger')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Button variant="ghost" size="sm" onClick={handleCancel} className="h-7 px-2">
                <IconX className="h-3.5 w-3.5 mr-1" />
                {t('cancel')}
              </Button>
              <Button size="sm" onClick={handleApply} className="h-7 px-3" disabled={!result.is_valid}>
                <IconCheck className="h-3.5 w-3.5 mr-1" />
                {t('apply')}
              </Button>
            </div>
          </div>

          <div className="text-sm text-foreground/90 whitespace-pre-line leading-relaxed bg-background/50 rounded-full p-3 border border-border/50">
            {locale === 'zh' ? result.explanation_zh : result.explanation_en}
          </div>

          {(() => {
            const sections: string[] = [];
            if (result.generated_config.permissions) sections.push(t('sectionPermissions'));
            if (result.generated_config.pathPolicy) sections.push(t('sectionPathPolicy'));
            if (result.generated_config.networkAllowlist) sections.push(t('sectionNetwork'));
            if (result.generated_config.privacyPolicy) sections.push(t('sectionPrivacy'));
            if (sections.length > 0) {
              return (
                <p className="text-xs text-muted-foreground">{t('willReplace', { sections: sections.join(', ') })}</p>
              );
            }
            return null;
          })()}

          {result.warnings.length > 0 && (
            <div className="space-y-1.5">
              {result.warnings.map((w, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-2 p-2 rounded-full text-xs ${
                    w.severity === 'danger'
                      ? 'bg-destructive/10 text-destructive border border-destructive/20'
                      : w.severity === 'warning'
                        ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800/50'
                        : 'bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800/50'
                  }`}
                >
                  <IconAlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                  <span>{w.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

NLPolicyGenerator.displayName = 'NLPolicyGenerator';

export default NLPolicyGenerator;
