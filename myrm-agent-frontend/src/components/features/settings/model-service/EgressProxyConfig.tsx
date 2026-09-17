'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Globe, Loader2, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { testProxyConnection, TestProxyResult } from '@/services/llm-config';

interface EgressProxyConfigProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  targetUrl?: string;
}

export const EgressProxyConfig = memo<EgressProxyConfigProps>(({
  value,
  onChange,
  disabled = false,
  targetUrl,
}) => {
  const t = useTranslations('settings.modelService');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestProxyResult | null>(null);

  const handleTestProxy = useCallback(async () => {
    const trimmed = value.trim();
    if (!trimmed || testing) {
      return;
    }

    setTesting(true);
    setTestResult(null);

    try {
      const res = await testProxyConnection(trimmed, targetUrl);
      setTestResult(res);
    } catch (err) {
      setTestResult({
        success: false,
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setTesting(false);
    }
  }, [value, testing, targetUrl]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
    if (testResult) {
      setTestResult(null);
    }
  }, [onChange, testResult]);

  return (
    <div className="space-y-3 pt-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-muted-foreground" />
          <h4 className="text-sm font-semibold text-foreground uppercase tracking-wide">
            {t('egressProxy')}
          </h4>
        </div>

        <button
          type="button"
          onClick={handleTestProxy}
          disabled={disabled || testing || !value.trim()}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-all whitespace-nowrap',
            testing
              ? 'border-primary/30 text-primary cursor-wait'
              : 'border-border/50 text-muted-foreground hover:text-primary hover:border-primary/50 hover:bg-primary/5',
            (!value.trim() || disabled) && 'opacity-40 cursor-not-allowed',
          )}
        >
          {testing ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <ShieldCheck className="w-3.5 h-3.5" />
          )}
          {t('testProxy')}
        </button>
      </div>

      <div className="space-y-1.5">
        <input
          type="text"
          value={value}
          onChange={handleInputChange}
          placeholder={t('egressProxyPlaceholder')}
          disabled={disabled}
          className="w-full px-3 py-2 text-sm bg-background border border-border/60 rounded-lg focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20 transition-all font-mono text-xs placeholder:font-sans placeholder:text-muted-foreground/60"
        />
        <p className="text-xs text-muted-foreground/80 leading-relaxed">
          {t('egressProxyDescription')}
        </p>
      </div>

      {testResult && (
        <div
          className={cn(
            'flex items-center gap-1.5 text-xs pt-0.5',
            testResult.success ? 'text-green-600 dark:text-green-400' : 'text-destructive',
          )}
        >
          {testResult.success ? (
            <>
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
              <span>
                {t('proxyConnected')}
                {testResult.latency_ms !== null && testResult.latency_ms !== undefined && ` (${testResult.latency_ms}ms)`}
              </span>
            </>
          ) : (
            <>
              <XCircle className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate max-w-md">
                {t('proxyFailed')}
                {testResult.error ? `: ${testResult.error}` : ''}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
});

EgressProxyConfig.displayName = 'EgressProxyConfig';
export default EgressProxyConfig;
