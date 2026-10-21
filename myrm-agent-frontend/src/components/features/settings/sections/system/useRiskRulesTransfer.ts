'use client';

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { apiRequest } from '@/lib/api';
import type { RiskRule } from './risk-rules-types';

/** Export of the custom rules to a JSON file and import of such a file; `reload` runs after an import. */
export function useRiskRulesTransfer(rules: RiskRule[], reload: () => void) {
  const t = useTranslations('settings.securityPolicy.riskRules');

  const handleExport = useCallback(() => {
    const customRules = rules.filter((r) => !r.is_builtin);
    if (customRules.length === 0) {
      toast.error(t('noCustomRulesToExport'));
      return;
    }
    const exportData = customRules.map(
      ({ rule_id, display_name, description, pattern, severity, category, sort_order }) => ({
        rule_id,
        display_name,
        description,
        pattern,
        severity,
        category,
        sort_order,
      }),
    );
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `risk-rules-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [rules, t]);

  const handleImport = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) {
        return;
      }
      try {
        const text = await file.text();
        const parsed = JSON.parse(text) as Array<Record<string, unknown>>;
        if (!Array.isArray(parsed)) {
          throw new Error('Invalid format');
        }
        const validRules = parsed.filter((r) => r.rule_id && r.pattern);
        if (validRules.length === 0) {
          toast.error(t('importError'));
          return;
        }
        const result = await apiRequest<{ imported: number; skipped: string[] }>('/risk/rules/batch-import', {
          method: 'POST',
          body: JSON.stringify({ rules: validRules }),
        });
        toast.success(t('importSuccess', { count: result.imported }));
        reload();
      } catch {
        toast.error(t('importError'));
      }
    };
    input.click();
  }, [reload, t]);

  return { handleExport, handleImport };
}
