'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { WeComCredentials } from '@/services/channels';
import { getWeComCredentials, saveWeComCredentials, testWeComConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: WeComCredentials = {
  corpId: '',
  corpSecret: '',
  agentId: '',
  token: '',
  encodingAesKey: '',
};

export function WeComConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<WeComCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['corpId', 'corpSecret'],
      getCreds: getWeComCredentials,
      saveCreds: saveWeComCredentials,
      testConnection: (c) => testWeComConnection(c.corpId, c.corpSecret),
      i18nPrefix: 'wecom',
    });

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ConnectionBadge status={connStatus} label={statusLabel} />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="wecom-corp-id">{t('wecomCorpId')}</Label>
          <Input
            id="wecom-corp-id"
            placeholder="ww..."
            value={creds.corpId}
            onChange={(e) => handleChange('corpId', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="wecom-corp-secret">{t('wecomCorpSecret')}</Label>
          <div className="relative">
            <Input
              id="wecom-corp-secret"
              type={showSecret ? 'text' : 'password'}
              placeholder="••••••••"
              value={creds.corpSecret}
              onChange={(e) => handleChange('corpSecret', e.target.value)}
              className="pr-10"
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
              onClick={() => setShowSecret(!showSecret)}
            >
              {showSecret ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="wecom-agent-id">{t('wecomAgentId')}</Label>
          <Input
            id="wecom-agent-id"
            placeholder="1000002"
            value={creds.agentId}
            onChange={(e) => handleChange('agentId', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="wecom-token">{t('wecomToken')}</Label>
          <Input
            id="wecom-token"
            placeholder={t('wecomTokenHint')}
            value={creds.token}
            onChange={(e) => handleChange('token', e.target.value)}
          />
        </div>

        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="wecom-aes-key">{t('wecomEncodingAesKey')}</Label>
          <Input
            id="wecom-aes-key"
            placeholder={t('wecomEncodingAesKeyHint')}
            value={creds.encodingAesKey}
            onChange={(e) => handleChange('encodingAesKey', e.target.value)}
          />
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('wecomSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.corpId || !creds.corpSecret}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('wecomTestConnection')}
        </Button>
      </div>
    </div>
  );
}
