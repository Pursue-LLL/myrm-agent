'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { EmailCredentials } from '@/services/channels';
import { getEmailCredentials, saveEmailCredentials, testEmailConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: EmailCredentials = {
  imapHost: '',
  imapPort: 993,
  smtpHost: '',
  smtpPort: 587,
  username: '',
  password: '',
};

export function EmailConfigCard() {
  const t = useTranslations('channels');
  const [showPassword, setShowPassword] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<EmailCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['imapHost', 'username', 'password'],
      getCreds: getEmailCredentials,
      saveCreds: saveEmailCredentials,
      testConnection: (c) => testEmailConnection(c.imapHost, c.imapPort, c.username, c.password),
      i18nPrefix: 'email',
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

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-lg">
        <div className="space-y-2">
          <Label htmlFor="email-imap-host">{t('emailImapHost')}</Label>
          <Input
            id="email-imap-host"
            placeholder="imap.gmail.com"
            value={creds.imapHost}
            onChange={(e) => handleChange('imapHost', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="email-imap-port">{t('emailImapPort')}</Label>
          <Input
            id="email-imap-port"
            type="number"
            value={creds.imapPort}
            onChange={(e) => handleChange('imapPort', parseInt(e.target.value) || 993)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="email-smtp-host">{t('emailSmtpHost')}</Label>
          <Input
            id="email-smtp-host"
            placeholder="smtp.gmail.com"
            value={creds.smtpHost}
            onChange={(e) => handleChange('smtpHost', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="email-smtp-port">{t('emailSmtpPort')}</Label>
          <Input
            id="email-smtp-port"
            type="number"
            value={creds.smtpPort}
            onChange={(e) => handleChange('smtpPort', parseInt(e.target.value) || 587)}
          />
        </div>
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="email-username">{t('emailUsername')}</Label>
        <Input
          id="email-username"
          placeholder="bot@example.com"
          value={creds.username}
          onChange={(e) => handleChange('username', e.target.value)}
        />
      </div>

      <div className="space-y-2 max-w-md">
        <Label htmlFor="email-password">{t('emailPassword')}</Label>
        <div className="relative">
          <Input
            id="email-password"
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
        <p className="text-xs text-muted-foreground">{t('emailPasswordHint')}</p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('emailSave')}
        </Button>
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={testing || !creds.imapHost || !creds.username || !creds.password}
          size="sm"
        >
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('emailTestConnection')}
        </Button>
      </div>
    </div>
  );
}
