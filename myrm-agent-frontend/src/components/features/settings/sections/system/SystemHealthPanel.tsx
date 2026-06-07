'use client';

/**
 * [INPUT]
 * - services/contextBundle::getContextBundleHealth, applyContextBundleMigration (POS: Context bundle health API client)
 * - SettingsSection (POS: Settings section layout shell)
 *
 * [OUTPUT]
 * - SystemHealthPanel: bundle-level system health for memory/workspace/offload/archive scenes
 *
 * [POS]
 * Developer settings diagnostics. Surfaces harness context bundle health (paths, ripgrep, migration).
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/primitives/alert-dialog';
import { IconActivity, IconAlertCircle, IconRefresh } from '@/components/features/icons/PremiumIcons';
import { toast } from '@/hooks/useToast';
import {
  applyContextBundleMigration,
  getContextBundleHealth,
  type ContextBundleHealth,
  type ContextBundleSceneHealth,
} from '@/services/contextBundle';
import SettingsSection from '../SettingsSection';

type SceneStatus = ContextBundleSceneHealth['index_status'];

const STATUS_STYLES: Record<SceneStatus, { badge: string; dot: string; ring: string }> = {
  ready: {
    badge: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
    dot: 'bg-emerald-500',
    ring: 'ring-emerald-500/20',
  },
  degraded: {
    badge: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
    dot: 'bg-amber-500',
    ring: 'ring-amber-500/25',
  },
  missing: {
    badge: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
    dot: 'bg-rose-500',
    ring: 'ring-rose-500/20',
  },
};

function resolveOverallStatus(health: ContextBundleHealth): SceneStatus {
  if (!health.writable || health.scenes.some((s) => s.index_status === 'missing')) {
    return 'missing';
  }
  if (health.scenes.some((s) => s.index_status === 'degraded') || health.warnings.length > 0) {
    return 'degraded';
  }
  return 'ready';
}

const SystemHealthPanel = memo(() => {
  const t = useTranslations('settings.developer.systemHealth');
  const [health, setHealth] = useState<ContextBundleHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [migrating, setMigrating] = useState(false);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getContextBundleHealth();
      setHealth(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  const handleMigrate = async () => {
    setMigrating(true);
    try {
      const result = await applyContextBundleMigration();
      if (result.ok) {
        toast({ title: t('migrateSuccess') });
      } else {
        toast({ title: t('migrateFailed'), variant: 'destructive' });
      }
      await loadHealth();
    } catch (err) {
      toast({
        title: t('migrateFailed'),
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setMigrating(false);
    }
  };

  const overall = health ? resolveOverallStatus(health) : null;
  const overallStyle = overall ? STATUS_STYLES[overall] : STATUS_STYLES.missing;

  const refreshAction = (
    <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void loadHealth()}>
      <IconRefresh className={cn('h-4 w-4 mr-1.5', loading && 'animate-spin')} />
      {t('refresh')}
    </Button>
  );

  return (
    <SettingsSection title={t('title')} description={t('description')} action={refreshAction}>
      {loading && !health ? (
        <div className="p-4 rounded-xl border border-border/40 bg-background/60 text-sm text-muted-foreground">
          {t('loading')}
        </div>
      ) : null}

      {error ? (
        <div className="flex items-start gap-2 p-4 rounded-xl border border-rose-500/30 bg-rose-500/5">
          <IconAlertCircle className="h-4 w-4 text-rose-500 mt-0.5 shrink-0" />
          <div className="space-y-1 min-w-0">
            <p className="text-sm font-medium text-rose-600 dark:text-rose-400">{t('loadFailed')}</p>
            <p className="text-xs text-muted-foreground break-all">{error}</p>
          </div>
        </div>
      ) : null}

      {health ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ring-1',
                overallStyle.badge,
                overallStyle.ring,
              )}
            >
              <IconActivity className="h-3.5 w-3.5" />
              {t(`status.${overall}`)}
            </span>
            <span
              className={cn(
                'inline-flex rounded-full px-2.5 py-1 text-xs font-medium',
                health.writable
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                  : 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
              )}
            >
              {health.writable ? t('writable') : t('notWritable')}
            </span>
            <span className="text-xs text-muted-foreground">
              {health.manifest_exists ? t('manifestOk') : t('manifestMissing')}
            </span>
          </div>

          <p className="text-xs text-muted-foreground leading-relaxed">
            {t('meta', {
              deploy: health.deploy_mode,
              storage: health.storage_mode,
              bundle: health.bundle_id,
            })}
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {health.scenes.map((scene) => (
              <SceneCard key={scene.scene} scene={scene} />
            ))}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-muted-foreground">
            <p className="font-mono break-all rounded-lg bg-background/50 px-3 py-2 border border-border/40">
              <span className="text-foreground/80 font-sans font-medium">{t('memoryPath')}: </span>
              {health.memory_base_path}
            </p>
            <p className="font-mono break-all rounded-lg bg-background/50 px-3 py-2 border border-border/40">
              <span className="text-foreground/80 font-sans font-medium">{t('harnessPath')}: </span>
              {health.harness_dir}
            </p>
          </div>

          {health.warnings.length > 0 ? (
            <div className="p-3 rounded-xl border border-amber-500/30 bg-amber-500/5 space-y-1">
              <p className="text-xs font-medium text-amber-700 dark:text-amber-300">{t('warnings')}</p>
              <ul className="text-xs text-muted-foreground list-disc pl-4 space-y-0.5">
                {health.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {health.migration_actions_pending > 0 ? (
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 rounded-xl border border-primary/20 bg-primary/5">
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">{t('migrationPending')}</p>
                <p className="text-xs text-muted-foreground">
                  {t('migrationCount', { count: health.migration_actions_pending })}
                </p>
              </div>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button type="button" size="sm" disabled={migrating}>
                    {t('applyMigration')}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t('migrateConfirmTitle')}</AlertDialogTitle>
                    <AlertDialogDescription>{t('migrateConfirmDesc')}</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                    <AlertDialogAction onClick={() => void handleMigrate()} disabled={migrating}>
                      {t('applyMigration')}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          ) : null}
        </div>
      ) : null}
    </SettingsSection>
  );
});

SystemHealthPanel.displayName = 'SystemHealthPanel';

export default SystemHealthPanel;

const SCENE_LABEL_KEYS = ['memory', 'workspace', 'offload', 'archive'] as const;
type SceneLabelKey = (typeof SCENE_LABEL_KEYS)[number];

function isSceneLabelKey(key: string): key is SceneLabelKey {
  return (SCENE_LABEL_KEYS as readonly string[]).includes(key);
}

function SceneCard({ scene }: { scene: ContextBundleSceneHealth }) {
  const t = useTranslations('settings.developer.systemHealth');
  const style = STATUS_STYLES[scene.index_status];
  const sceneKey = scene.scene.toLowerCase();
  const sceneLabel = isSceneLabelKey(sceneKey) ? t(`scenes.${sceneKey}`) : scene.scene;
  const isWorkspaceDegraded = sceneKey === 'workspace' && scene.index_status === 'degraded';

  return (
    <div
      className={cn(
        'p-4 rounded-xl border border-border/50 bg-background/40 backdrop-blur-sm space-y-2 ring-1',
        style.ring,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-foreground">{sceneLabel}</span>
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
            style.badge,
          )}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', style.dot)} />
          {t(`sceneStatus.${scene.index_status}`)}
        </span>
      </div>
      <p className="text-xs text-muted-foreground font-mono break-all">{scene.path}</p>
      {isWorkspaceDegraded ? (
        <p className="text-xs text-amber-700 dark:text-amber-300 leading-relaxed">{t('ripgrepHint')}</p>
      ) : null}
    </div>
  );
}
