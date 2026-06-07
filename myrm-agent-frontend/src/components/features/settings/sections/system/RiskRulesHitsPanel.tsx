'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { IconLoader } from '@/components/features/icons/PremiumIcons';
import { apiRequest } from '@/lib/api';
import { SEVERITY_COLORS, ACTION_COLORS, type RiskHit } from './risk-rules-types';

function RiskRulesHitsPanel() {
  const t = useTranslations('settings.securityPolicy.riskRules');
  const [hits, setHits] = useState<RiskHit[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadHits = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiRequest<{ list: RiskHit[]; total: number }>('/risk/hits?limit=50');
      setHits(result.list || []);
      setTotal(result.total || 0);
    } catch {
      toast.error(t('loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadHits();
  }, [loadHits]);

  return (
    <div className="border border-border rounded-lg p-4 mb-4 bg-card">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium text-sm">{t('hitsTitle')}</h3>
        <span className="text-xs text-muted-foreground">{t('hitsTotal', { count: total })}</span>
      </div>
      {loading ? (
        <div className="flex justify-center py-4">
          <IconLoader className="w-5 h-5 animate-spin" />
        </div>
      ) : hits.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-4">{t('hitsEmpty')}</p>
      ) : (
        <div className="space-y-2 max-h-[300px] overflow-y-auto">
          {hits.map((h) => (
            <div key={h.id} className="flex items-center gap-3 text-xs border-b border-border pb-2">
              <span className="font-medium flex-shrink-0">{h.rule_name}</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${SEVERITY_COLORS[h.severity] || ''}`}>
                {t(
                  `severity${h.severity.charAt(0).toUpperCase() + h.severity.slice(1)}` as
                    | 'severityLow'
                    | 'severityMedium'
                    | 'severityHigh',
                )}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${ACTION_COLORS[h.action] || ''}`}>
                {t(`action${h.action.charAt(0).toUpperCase() + h.action.slice(1)}` as 'actionAllow' | 'actionBlock')}
              </span>
              <code className="text-muted-foreground truncate flex-1">{h.match_summary}</code>
              <span className="text-muted-foreground flex-shrink-0">
                {h.created_at ? new Date(h.created_at).toLocaleString() : '-'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default memo(RiskRulesHitsPanel);
