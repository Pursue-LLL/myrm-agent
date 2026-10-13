/**
 * [INPUT]
 * - ../catalog-types (POS: 目录条目与凭证字段类型)
 * - ../catalog-icons::IconExternalLink (POS: 外链图标)
 * - @/components/primitives/input|label (POS: 表单原语)
 *
 * [OUTPUT]
 * - AuthSection: 按条目认证方式渲染连接对话框的认证区（免认证说明 / 单字段与多字段凭证输入）
 *
 * [POS]
 * 连接对话框的展示层：受控输入的状态由父级持有，本组件只负责按认证方式分支渲染与本地化标签。
 */
'use client';

import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { IconExternalLink } from '../catalog-icons';
import type { CatalogEntry, CredentialField } from '../catalog-types';

interface AuthSectionProps {
  entry: CatalogEntry;
  locale: string;
  credentialFields: CredentialField[];
  credential: string;
  fieldValues: Record<string, string>;
  helpText: string | null;
  onCredentialChange: (value: string) => void;
  onFieldChange: (key: string, value: string) => void;
}

function HelpLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary inline-flex items-center gap-1 text-xs hover:underline"
    >
      {label}
      <IconExternalLink className="h-3 w-3" />
    </a>
  );
}

function NoAuthNotice({ helpText, helpUrl }: { helpText: string | null; helpUrl: string | null }) {
  const t = useTranslations('settings.integrationCatalog.connectDialog');
  return (
    <div className="space-y-2">
      {helpText ? (
        <p className="text-muted-foreground text-xs">{helpText}</p>
      ) : (
        <p className="text-muted-foreground text-sm">{t('noAuthRequired')}</p>
      )}
      {helpUrl && <HelpLink href={helpUrl} label={t('learnMore')} />}
    </div>
  );
}

function CredentialInputs({
  locale,
  credentialFields,
  credential,
  fieldValues,
  helpText,
  helpUrl,
  onCredentialChange,
  onFieldChange,
}: Omit<AuthSectionProps, 'entry'> & { helpUrl: string | null }) {
  const t = useTranslations('settings.integrationCatalog.connectDialog');
  return (
    <>
      {credentialFields.length > 0 ? (
        <div className="space-y-3">
          {credentialFields.map((field) => {
            const label = locale === 'zh' && field.labelZh ? field.labelZh : field.label;
            return (
              <div key={field.key} className="space-y-1.5">
                <Label className="text-sm">{label}</Label>
                <Input
                  type="password"
                  value={fieldValues[field.key] || ''}
                  onChange={(e) => onFieldChange(field.key, e.target.value)}
                  placeholder={label}
                />
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-2">
          <Label>{t('credentialLabel')}</Label>
          <Input
            type="password"
            value={credential}
            onChange={(e) => onCredentialChange(e.target.value)}
            placeholder={t('credentialPlaceholder')}
          />
        </div>
      )}

      {helpText && <p className="text-muted-foreground text-xs">{helpText}</p>}

      {helpUrl && <HelpLink href={helpUrl} label={t('getCredential')} />}
    </>
  );
}

export function AuthSection({ entry, ...credentialProps }: AuthSectionProps) {
  if (entry.authType === 'none') {
    return <NoAuthNotice helpText={credentialProps.helpText} helpUrl={entry.helpUrl} />;
  }
  return <CredentialInputs {...credentialProps} helpUrl={entry.helpUrl} />;
}
