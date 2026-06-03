'use client';

import { memo, useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { apiRequest } from '@/lib/api';

function RiskRulesTestPanel() {
  const t = useTranslations('settings.securityPolicy.riskRules');
  const [pattern, setPattern] = useState('');
  const [text, setText] = useState('');
  const [results, setResults] = useState<string[] | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runTest = useCallback(async (p: string, txt: string) => {
    if (!p || !txt) {
      setResults(null);
      return;
    }
    try {
      const result = await apiRequest<{ matches: string[]; count: number }>('/risk/rules/test', {
        method: 'POST',
        body: JSON.stringify({ pattern: p, test_text: txt }),
      });
      setResults(result.matches);
    } catch {
      setResults([]);
    }
  }, []);

  const debouncedTest = useCallback(
    (p: string, txt: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => runTest(p, txt), 500);
    },
    [runTest],
  );

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  return (
    <div className="border border-border rounded-lg p-4 mb-4 space-y-3 bg-card">
      <h3 className="font-medium text-sm">{t('testTitle')}</h3>
      <div className="space-y-2">
        <Input
          placeholder={t('testPattern')}
          value={pattern}
          onChange={(e) => {
            setPattern(e.target.value);
            debouncedTest(e.target.value, text);
          }}
          className="font-mono text-sm"
        />
        <textarea
          placeholder={t('testText')}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            debouncedTest(pattern, e.target.value);
          }}
          className="w-full min-h-[80px] p-2 border border-border rounded-full bg-background text-sm resize-y"
        />
        <Button size="sm" onClick={() => runTest(pattern, text)} disabled={!pattern || !text}>
          {t('testSubmit')}
        </Button>
      </div>
      {results !== null && (
        <div className="mt-2">
          {results.length > 0 ? (
            <div className="space-y-1">
              <p className="text-sm font-medium">
                {t('testMatches')} ({results.length}):
              </p>
              {results.map((m, i) => (
                <code key={i} className="block text-xs bg-muted px-2 py-1 rounded">
                  {m}
                </code>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('testNoMatches')}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default memo(RiskRulesTestPanel);
