'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import { IconAlertTriangle, IconGlow } from '@/components/features/icons/PremiumIcons';
import { toast } from 'sonner';
import { Switch } from '@/components/primitives/switch';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import SettingsSection from '../SettingsSection';

interface FeatureItem {
  id: string;
  key: string;
  description: string;
  stage: string;
  enabled: boolean;
  default_enabled: boolean;
  is_overridden: boolean;
  experimental_name: string | null;
  experimental_description: string | null;
  announcement: string | null;
  deprecation_hint: string | null;
}

interface FeaturesResponse {
  features: FeatureItem[];
  warnings: string[];
}

const ExperimentalFeaturesSection = memo(() => {
  const t = useTranslations('settings.experimentalFeatures');
  const [features, setFeatures] = useState<FeatureItem[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [togglingIds, setTogglingIds] = useState<Set<string>>(new Set());

  const fetchFeatures = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/features/experimental');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: FeaturesResponse = await res.json();
      setFeatures(data.features);
      setWarnings(data.warnings);
    } catch {
      toast.error(t('fetchError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchFeatures();
  }, [fetchFeatures]);

  const handleToggle = useCallback(
    async (featureId: string, enabled: boolean) => {
      setTogglingIds((prev) => new Set(prev).add(featureId));

      try {
        const res = await fetch(`/api/v1/features/${featureId}/toggle`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }

        setFeatures((prev) => prev.map((f) => (f.id === featureId ? { ...f, enabled, is_overridden: true } : f)));

        toast.success(enabled ? t('enabledSuccess', { name: featureId }) : t('disabledSuccess', { name: featureId }));
      } catch {
        toast.error(t('toggleError', { name: featureId }));
      } finally {
        setTogglingIds((prev) => {
          const next = new Set(prev);
          next.delete(featureId);
          return next;
        });
      }
    },
    [t],
  );

  if (loading) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between py-2">
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-52" />
              </div>
              <Skeleton className="h-6 w-10 rounded-full" />
            </div>
          ))}
        </div>
      </SettingsSection>
    );
  }

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      {warnings.length > 0 && (
        <div className="mb-4 p-3 rounded-lg bg-warning/10 border border-warning/30 flex items-start gap-2">
          <IconAlertTriangle className="w-4 h-4 text-warning mt-0.5 shrink-0" />
          <div className="text-sm text-warning">
            {warnings.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
          </div>
        </div>
      )}

      {features.length === 0 ? (
        <p className="text-muted-foreground text-sm py-8 text-center">{t('noFeatures')}</p>
      ) : (
        <div className="space-y-3">
          {features.map((feature) => (
            <div
              key={feature.id}
              className={cn(
                'flex items-start justify-between gap-4 p-4 rounded-lg border transition-colors',
                feature.enabled ? 'bg-primary/5 border-primary/20' : 'bg-card border-border hover:border-primary/20',
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h4 className="font-medium text-sm">{feature.experimental_name || feature.id}</h4>
                  <Badge variant="outline" className="text-xs shrink-0">
                    {t('experimentalBadge')}
                  </Badge>
                  {feature.announcement && (
                    <Badge className="text-xs bg-primary/10 text-primary border-primary/20 shrink-0">
                      <IconGlow className="w-2.5 h-2.5 mr-1" />
                      {t('newBadge')}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {feature.experimental_description || feature.description}
                </p>
                {feature.is_overridden && (
                  <p className="text-xs text-muted-foreground/70 mt-1 italic">{t('customized')}</p>
                )}
              </div>
              <Switch
                checked={feature.enabled}
                onCheckedChange={(checked) => handleToggle(feature.id, checked)}
                disabled={togglingIds.has(feature.id)}
              />
            </div>
          ))}
        </div>
      )}
    </SettingsSection>
  );
});

ExperimentalFeaturesSection.displayName = 'ExperimentalFeaturesSection';

export default ExperimentalFeaturesSection;
