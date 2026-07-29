'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Globe, Loader2 } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/shared/useToast';
import { getUserSkillConfig, updateUserSkillConfig } from '@/services/skill';

type MirrorPreset = 'intl' | 'cn' | 'custom';

interface RegistryPreset {
  id: string;
  url: string;
}

const DEFAULT_PRESETS: RegistryPreset[] = [
  { id: 'intl', url: '' },
  { id: 'cn', url: 'https://skill.xfyun.cn' },
];

function resolvePresetFromUrl(
  url: string,
  presets: RegistryPreset[],
): { preset: MirrorPreset; customUrl: string } {
  const normalized = url.trim();
  const cnPreset = presets.find((item) => item.id === 'cn');
  if (!normalized) {
    return { preset: 'intl', customUrl: '' };
  }
  if (cnPreset && normalized === cnPreset.url.trim()) {
    return { preset: 'cn', customUrl: '' };
  }
  return { preset: 'custom', customUrl: normalized };
}

function urlForPreset(preset: MirrorPreset, presets: RegistryPreset[], customUrl: string): string {
  if (preset === 'cn') {
    return presets.find((item) => item.id === 'cn')?.url ?? '';
  }
  if (preset === 'custom') {
    return customUrl.trim();
  }
  return '';
}

async function probeRegistry(targetUrl: string): Promise<boolean> {
  const params = new URLSearchParams();
  if (targetUrl.trim()) {
    params.set('url', targetUrl.trim());
  } else {
    params.set('mirror', 'intl');
  }
  const probe = await fetch(`/api/v1/skills/discovery/registry-probe?${params.toString()}`);
  if (!probe.ok) {
    return false;
  }
  const body = (await probe.json()) as { reachable?: boolean };
  return body.reachable === true;
}

const SkillRegistryMirrorPanel = memo(() => {
  const t = useTranslations('settings.skills.discover.registryMirror');
  const [presets, setPresets] = useState<RegistryPreset[]>(DEFAULT_PRESETS);
  const [preset, setPreset] = useState<MirrorPreset>('intl');
  const [customUrl, setCustomUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const cnPresetUrl = useMemo(
    () => presets.find((item) => item.id === 'cn')?.url ?? '',
    [presets],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const config = await getUserSkillConfig();
        const loadedPresets =
          config.registry_presets && config.registry_presets.length > 0
            ? config.registry_presets
            : DEFAULT_PRESETS;
        if (!cancelled) {
          setPresets(loadedPresets);
          const resolved = resolvePresetFromUrl(
            config.clawhub_registry_url ?? '',
            loadedPresets,
          );
          setPreset(resolved.preset);
          setCustomUrl(resolved.customUrl);
        }
      } catch {
        // keep default
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const persistMirror = useCallback(
    async (nextPreset: MirrorPreset, nextCustomUrl: string) => {
      const targetUrl = urlForPreset(nextPreset, presets, nextCustomUrl);
      if (nextPreset === 'custom' && !targetUrl) {
        toast({ title: t('customUrlRequired'), variant: 'destructive' });
        return;
      }

      setSaving(true);
      try {
        const reachable = await probeRegistry(
          nextPreset === 'cn' ? cnPresetUrl : targetUrl,
        );
        if (!reachable) {
          toast({
            title: t('mirrorUnreachable'),
            description: t('saveFailed'),
            variant: 'destructive',
          });
          return;
        }
        await updateUserSkillConfig({ clawhub_registry_url: targetUrl });
        setPreset(nextPreset);
        setCustomUrl(nextPreset === 'custom' ? targetUrl : '');
        toast({ title: t('saved') });
      } catch {
        toast({ title: t('saveFailed'), variant: 'destructive' });
      } finally {
        setSaving(false);
      }
    },
    [cnPresetUrl, presets, t],
  );

  const handlePresetChange = useCallback(
    async (value: MirrorPreset) => {
      if (value === 'custom') {
        setPreset('custom');
        return;
      }
      await persistMirror(value, customUrl);
    },
    [customUrl, persistMirror],
  );

  const handleCustomSave = useCallback(async () => {
    await persistMirror('custom', customUrl);
  }, [customUrl, persistMirror]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border px-3 py-3 bg-card">
      <div className="flex items-center gap-2">
        <Globe className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">{t('title')}</span>
      </div>
      <p className="text-xs text-muted-foreground">{t('description')}</p>
      <Select
        value={preset}
        onValueChange={(value) => handlePresetChange(value as MirrorPreset)}
        disabled={saving}
      >
        <SelectTrigger className="h-8 text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="intl">{t('intl')}</SelectItem>
          <SelectItem value="cn">{t('cn')}</SelectItem>
          <SelectItem value="custom">{t('custom')}</SelectItem>
        </SelectContent>
      </Select>
      {preset === 'custom' && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Input
            value={customUrl}
            onChange={(event) => setCustomUrl(event.target.value)}
            placeholder={t('customUrlPlaceholder')}
            className="h-8 text-sm flex-1 min-w-0"
            disabled={saving}
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={handleCustomSave}
            disabled={saving || !customUrl.trim()}
            className="shrink-0 w-full sm:w-auto"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t('customSave')}
          </Button>
        </div>
      )}
    </div>
  );
});

SkillRegistryMirrorPanel.displayName = 'SkillRegistryMirrorPanel';
export default SkillRegistryMirrorPanel;
