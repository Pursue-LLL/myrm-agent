'use client';

/**
 * [INPUT] @/services/agent::OpenAPIAuthConfig, OpenAPIAuthType (POS: OpenAPI 服务鉴权配置类型)
 * [OUTPUT] AuthEditor: OpenAPI 服务鉴权编辑器（选择鉴权类型并填写该类型所需的凭据字段）
 * [POS] ServiceEditor 展开后的鉴权区，字段变化经 onChange 回传给上层。
 */

import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { type OpenAPIAuthType, type OpenAPIAuthConfig } from '@/services/agent';

export function AuthEditor({
  auth,
  onChange,
  readonly,
}: {
  auth?: OpenAPIAuthConfig;
  onChange: (auth: OpenAPIAuthConfig | undefined) => void;
  readonly?: boolean;
}) {
  const t = useTranslations('agent.openapi.auth');
  const currentType = auth?.type || 'none';

  const setType = (type: OpenAPIAuthType) => {
    if (type === 'none') {
      onChange(undefined);
    } else {
      onChange({ ...auth, type });
    }
  };

  return (
    <div className="mt-2 space-y-2 pl-2 border-l-2 border-border/30">
      <select
        value={currentType}
        onChange={(e) => setType(e.target.value as OpenAPIAuthType)}
        disabled={readonly}
        className="w-full h-8 rounded-full border border-input bg-background px-2 text-xs"
      >
        <option value="none">{t('none')}</option>
        <option value="api_key">{t('apiKey')}</option>
        <option value="bearer">{t('bearer')}</option>
        <option value="basic">{t('basic')}</option>
        <option value="oauth2_client_credentials">{t('oauth2')}</option>
      </select>

      {currentType === 'api_key' && (
        <div className="space-y-2">
          <Input
            placeholder={t('apiKeyHeader')}
            value={auth?.api_key_header || ''}
            onChange={(e) => onChange({ type: currentType, ...auth, api_key_header: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
          <Input
            type="password"
            placeholder={t('apiKeyValue')}
            value={auth?.api_key || ''}
            onChange={(e) => onChange({ type: currentType, ...auth, api_key: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
        </div>
      )}

      {currentType === 'bearer' && (
        <Input
          type="password"
          placeholder={t('bearerToken')}
          value={auth?.bearer_token || ''}
          onChange={(e) => onChange({ type: currentType, ...auth, bearer_token: e.target.value })}
          disabled={readonly}
          className="text-xs h-8"
        />
      )}

      {currentType === 'basic' && (
        <div className="grid grid-cols-2 gap-2">
          <Input
            placeholder={t('username')}
            value={auth?.username || ''}
            onChange={(e) => onChange({ type: currentType, ...auth, username: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
          <Input
            type="password"
            placeholder={t('password')}
            value={auth?.password || ''}
            onChange={(e) => onChange({ type: currentType, ...auth, password: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
        </div>
      )}

      {currentType === 'oauth2_client_credentials' && (
        <div className="space-y-2">
          <Input
            placeholder={t('tokenUrl')}
            value={auth?.token_url || ''}
            onChange={(e) => onChange({ type: currentType, ...auth, token_url: e.target.value })}
            disabled={readonly}
            className="text-xs h-8"
          />
          <div className="grid grid-cols-2 gap-2">
            <Input
              placeholder={t('clientId')}
              value={auth?.client_id || ''}
              onChange={(e) => onChange({ type: currentType, ...auth, client_id: e.target.value })}
              disabled={readonly}
              className="text-xs h-8"
            />
            <Input
              type="password"
              placeholder={t('clientSecret')}
              value={auth?.client_secret || ''}
              onChange={(e) => onChange({ type: currentType, ...auth, client_secret: e.target.value })}
              disabled={readonly}
              className="text-xs h-8"
            />
          </div>
          <Input
            placeholder={t('scopes')}
            value={(auth?.scopes || []).join(', ')}
            onChange={(e) =>
              onChange({
                type: currentType,
                ...auth,
                scopes: e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            disabled={readonly}
            className="text-xs h-8"
          />
        </div>
      )}
    </div>
  );
}
