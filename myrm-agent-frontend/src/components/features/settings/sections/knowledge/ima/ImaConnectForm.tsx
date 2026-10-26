'use client';

/**
 * [INPUT]
 * @/services/wiki/ima::ImaCredentialsInput (POS: connect payload)
 *
 * [OUTPUT]
 * ImaConnectForm: client id + API key form for first connect and for reconnecting after ima rejected the key
 *
 * [POS]
 * First screen of the ima card. The key is write-only: it is typed here, sent once and never shown again, so the form
 * keeps it in local state only; it is dropped with the form once the connection succeeds, and kept on failure so a typo is fixed in place.
 */

import { useState, type FormEvent } from 'react';
import { useTranslations } from 'next-intl';
import { Alert } from '@/components/primitives/alert';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import type { ImaCredentialsInput } from '@/services/wiki/ima';

/** ima's own page where a user creates the Client ID / API Key pair. */
const IMA_CREDENTIALS_URL = 'https://ima.qq.com/agent-interface';

interface ImaConnectFormProps {
  /** ima rejected the stored key, so the form explains why it is being shown again. */
  reconnect: boolean;
  busy: boolean;
  /** Locale key (relative to `settings.wiki.ima`) of the last failure. */
  errorKey: string | null;
  onSubmit: (input: ImaCredentialsInput) => Promise<void>;
}

export default function ImaConnectForm({ reconnect, busy, errorKey, onSubmit }: ImaConnectFormProps) {
  const t = useTranslations('settings.wiki.ima');
  const [clientId, setClientId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const canSubmit = !busy && clientId.trim() !== '' && apiKey.trim() !== '';

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    await onSubmit({ client_id: clientId.trim(), api_key: apiKey.trim() });
  };

  return (
    <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
      {reconnect ? <Alert variant="warning">{t('connect.reconnectNotice')}</Alert> : null}
      <div className="space-y-1.5">
        <p className="text-sm text-muted-foreground">{t('connect.hint')}</p>
        <a
          href={IMA_CREDENTIALS_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block text-sm text-primary underline-offset-4 hover:underline"
        >
          {t('connect.getCredentials')}
        </a>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="ima-client-id">{t('connect.clientIdLabel')}</Label>
          <Input
            id="ima-client-id"
            value={clientId}
            autoComplete="off"
            spellCheck={false}
            placeholder={t('connect.clientIdPlaceholder')}
            onChange={(event) => setClientId(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ima-api-key">{t('connect.apiKeyLabel')}</Label>
          <Input
            id="ima-api-key"
            type="password"
            value={apiKey}
            autoComplete="new-password"
            spellCheck={false}
            placeholder={t('connect.apiKeyPlaceholder')}
            onChange={(event) => setApiKey(event.target.value)}
          />
        </div>
      </div>
      {errorKey ? (
        <p role="alert" className="text-sm text-destructive">
          {t(errorKey)}
        </p>
      ) : null}
      <Button type="submit" size="sm" disabled={!canSubmit}>
        {busy ? t('connect.submitting') : t('connect.submit')}
      </Button>
    </form>
  );
}
