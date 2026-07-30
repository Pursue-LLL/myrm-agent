'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { Textarea } from '@/components/primitives/textarea';
import {
  getWikiSourceSyncStatus,
  syncWikiSources,
  updateWikiSourceSyncConfig,
  type WikiSourceSyncStatus,
} from '@/services/wikiSourceSync';
import { useWikiAgentScope } from './WikiAgentScopeContext';

interface WikiSourceSyncPanelProps {
  onGoToIntegrations?: () => void;
}

export default function WikiSourceSyncPanel({ onGoToIntegrations }: WikiSourceSyncPanelProps) {
  const t = useTranslations('settings.wiki.sources');
  const { agentScopeId } = useWikiAgentScope();
  const [status, setStatus] = useState<WikiSourceSyncStatus | null>(null);
  const [rssText, setRssText] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getWikiSourceSyncStatus(agentScopeId);
      setStatus(data);
      setRssText(data.config.rss_feeds.join('\n'));
    } catch {
      toast.error(t('loadError'));
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [agentScopeId, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleSave = useCallback(async () => {
    if (!status) return;
    const feeds = rssText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    try {
      setSaving(true);
      const updated = await updateWikiSourceSyncConfig(
        {
          gmail_enabled: status.config.gmail_enabled,
          gmail_label: status.config.gmail_label,
          rss_feeds: feeds,
          auto_compile: status.config.auto_compile,
          max_items_per_run: status.config.max_items_per_run,
          mirror_integrations_to_wiki: status.config.mirror_integrations_to_wiki,
        },
        agentScopeId,
      );
      setStatus(updated);
      toast.success(t('saveSuccess'));
    } catch {
      toast.error(t('saveError'));
    } finally {
      setSaving(false);
    }
  }, [agentScopeId, rssText, status, t]);

  const handleSync = useCallback(async () => {
    try {
      setSyncing(true);
      const summary = await syncWikiSources(agentScopeId);
      if (summary.total_published > 0) {
        toast.success(t('syncSuccess', { count: summary.total_published }));
      } else {
        toast.message(t('syncEmpty'));
      }
      await refresh();
    } catch {
      toast.error(t('syncError'));
    } finally {
      setSyncing(false);
    }
  }, [agentScopeId, refresh, t]);

  if (loading && !status) {
    return null;
  }

  if (!status) {
    return null;
  }

  return (
    <Card className="border-border/60 bg-card/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{t('title')}</CardTitle>
        <CardDescription>{t('description')}</CardDescription>
        {status.state.last_sync_at ? (
          <p className="text-xs text-muted-foreground">
            {t('lastSync', { time: new Date(status.state.last_sync_at).toLocaleString() })}
            {' · '}
            {t('lastSyncSummary', {
              published: status.state.total_published,
              skipped: status.state.total_skipped,
              failed: status.state.total_failed,
            })}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">{t('lastSyncNever')}</p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div className="space-y-0.5">
            <Label htmlFor="wiki-gmail-enabled">{t('gmailLabel')}</Label>
            <p className="text-xs text-muted-foreground">
              {status.google_connected ? t('googleConnected') : t('googleDisconnected')}
            </p>
          </div>
          <Switch
            id="wiki-gmail-enabled"
            checked={status.config.gmail_enabled}
            disabled={!status.google_connected}
            onCheckedChange={(checked) =>
              setStatus((prev) =>
                prev
                  ? { ...prev, config: { ...prev.config, gmail_enabled: checked } }
                  : prev,
              )
            }
          />
        </div>

        {status.config.gmail_enabled && (
          <div className="space-y-2">
            <Label htmlFor="wiki-gmail-label">{t('gmailTagLabel')}</Label>
            <Input
              id="wiki-gmail-label"
              value={status.config.gmail_label}
              onChange={(event) =>
                setStatus((prev) =>
                  prev
                    ? { ...prev, config: { ...prev.config, gmail_label: event.target.value } }
                    : prev,
                )
              }
            />
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="wiki-rss-feeds">{t('rssFeedsLabel')}</Label>
          <Textarea
            id="wiki-rss-feeds"
            value={rssText}
            onChange={(event) => setRssText(event.target.value)}
            rows={3}
            placeholder={t('rssFeedsPlaceholder')}
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="wiki-auto-compile">{t('autoCompile')}</Label>
          <Switch
            id="wiki-auto-compile"
            checked={status.config.auto_compile}
            onCheckedChange={(checked) =>
              setStatus((prev) =>
                prev ? { ...prev, config: { ...prev.config, auto_compile: checked } } : prev,
              )
            }
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="wiki-mirror-integrations">{t('mirrorIntegrations')}</Label>
          <Switch
            id="wiki-mirror-integrations"
            checked={status.config.mirror_integrations_to_wiki}
            onCheckedChange={(checked) =>
              setStatus((prev) =>
                prev
                  ? { ...prev, config: { ...prev.config, mirror_integrations_to_wiki: checked } }
                  : prev,
              )
            }
          />
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          <Button type="button" variant="secondary" size="sm" disabled={saving} onClick={() => void handleSave()}>
            {saving ? t('saving') : t('save')}
          </Button>
          <Button type="button" size="sm" disabled={syncing} onClick={() => void handleSync()}>
            {syncing ? t('syncing') : t('syncNow')}
          </Button>
          {onGoToIntegrations && !status.google_connected && (
            <Button type="button" variant="outline" size="sm" onClick={onGoToIntegrations}>
              {t('connectGoogle')}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
