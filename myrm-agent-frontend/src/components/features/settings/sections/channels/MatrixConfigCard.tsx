'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import type { MatrixCredentials } from '@/services/channels';
import { getMatrixCredentials, saveMatrixCredentials, testMatrixConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: MatrixCredentials = {
  homeserverUrl: '',
  accessToken: '',
  deviceId: '',
  userId: '',
  password: '',
  encryption: false,
  proxy: '',
};

export function MatrixConfigCard() {
  const t = useTranslations('channels');
  const [showSecret, setShowSecret] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<MatrixCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['homeserverUrl'],
      getCreds: getMatrixCredentials,
      saveCreds: saveMatrixCredentials,
      testConnection: (c) => testMatrixConnection(c.homeserverUrl, c.accessToken),
      i18nPrefix: 'matrix',
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
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="matrix-homeserver">{t('matrixHomeserverUrl')}</Label>
          <Input
            id="matrix-homeserver"
            placeholder="https://matrix.org"
            value={creds.homeserverUrl}
            onChange={(e) => handleChange('homeserverUrl', e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="matrix-user-id">{t('matrixUserId')}</Label>
          <Input
            id="matrix-user-id"
            placeholder={t('matrixUserIdPlaceholder')}
            value={creds.userId}
            onChange={(e) => handleChange('userId', e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('matrixUserIdHint')}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="matrix-access-token">{t('matrixAccessToken')}</Label>
          <div className="relative">
            <Input
              id="matrix-access-token"
              type={showSecret ? 'text' : 'password'}
              placeholder="••••••••"
              value={creds.accessToken}
              onChange={(e) => handleChange('accessToken', e.target.value)}
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
          <Label htmlFor="matrix-password">{t('matrixPassword')}</Label>
          <div className="relative">
            <Input
              id="matrix-password"
              type={showPassword ? 'text' : 'password'}
              placeholder="••••••••"
              value={creds.password}
              onChange={(e) => handleChange('password', e.target.value)}
              className="pr-10"
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
            </button>
          </div>
          <p className="text-xs text-muted-foreground">{t('matrixPasswordHint')}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="matrix-device-id">{t('matrixDeviceId')}</Label>
          <Input
            id="matrix-device-id"
            placeholder="ABCDEFGH"
            value={creds.deviceId}
            onChange={(e) => handleChange('deviceId', e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('matrixDeviceIdHint')}</p>
        </div>
      </div>

      {/* E2EE Settings */}
      <div className="space-y-3 rounded-full border border-border/50 p-3">
        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="matrix-encryption">{t('matrixEncryption')}</Label>
            <p className="text-xs text-muted-foreground">{t('matrixEncryptionHint')}</p>
          </div>
          <Switch
            id="matrix-encryption"
            checked={creds.encryption}
            onCheckedChange={(v) => handleChange('encryption', v)}
          />
        </div>
      </div>

      {/* Proxy Settings */}
      <div className="space-y-2">
        <Label htmlFor="matrix-proxy">{t('matrixProxy')}</Label>
        <Input
          id="matrix-proxy"
          placeholder="http://proxy:8080 or socks5://proxy:1080"
          value={creds.proxy}
          onChange={(e) => handleChange('proxy', e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t('matrixProxyHint')}</p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('matrixSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.homeserverUrl || (!creds.accessToken && !creds.password)}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('matrixTestConnection')}
        </Button>
      </div>
    </div>
  );
}
