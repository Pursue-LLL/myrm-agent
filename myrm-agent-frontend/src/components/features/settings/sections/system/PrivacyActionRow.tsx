'use client';

/**
 * [INPUT]
 *   next-intl useTranslations
 *   PremiumIcons, shadcn Select
 *   services/config/types::PIIAction (POS: 隐私处理方式取值)
 * [OUTPUT]
 *   PrivacyActionRow: 一个敏感级别的处理方式选择行，并在下方说明所选方式的实际后果
 * [POS]
 *   隐私保护设置面板的 S2/S3 处理方式行；说明文案与后端实际行为一一对应，避免用户误以为"开了就万无一失"
 */

import { memo, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { IconBan, IconEyeOff, IconRefresh, IconShieldAlert } from '@/components/features/icons/PremiumIcons';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import type { PIIAction } from '@/services/config/types';

const ACTION_OPTIONS = [
  { value: 'warn', labelKey: 'actionWarn', Icon: IconShieldAlert, iconClass: 'text-amber-500' },
  { value: 'pseudonymize', labelKey: 'actionPseudonymize', Icon: IconRefresh, iconClass: 'text-emerald-500' },
  { value: 'redact', labelKey: 'actionRedact', Icon: IconEyeOff, iconClass: 'text-blue-500' },
  { value: 'block', labelKey: 'actionBlock', Icon: IconBan, iconClass: 'text-destructive' },
] as const satisfies ReadonlyArray<{ value: PIIAction; labelKey: string; Icon: typeof IconBan; iconClass: string }>;

interface PrivacyActionRowProps {
  icon: ReactNode;
  label: string;
  value: PIIAction;
  onChange: (action: PIIAction) => void;
}

const PrivacyActionRow = memo(({ icon, label, value, onChange }: PrivacyActionRowProps) => {
  const t = useTranslations('settings.securityPolicy.privacy');

  return (
    <div className="grid grid-cols-1 sm:grid-cols-[180px_minmax(0,1fr)] sm:items-center gap-x-2 gap-y-1.5">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-sm text-foreground">{label}</span>
      </div>
      <Select value={value} onValueChange={(next: string) => onChange(next as PIIAction)}>
        <SelectTrigger className="w-44">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {ACTION_OPTIONS.map(({ value: option, labelKey, Icon, iconClass }) => (
            <SelectItem key={option} value={option}>
              <span className="flex items-center gap-1.5">
                <Icon className={`h-3.5 w-3.5 ${iconClass}`} />
                {t(labelKey)}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground sm:col-start-2">{t(`consequence.${value}`)}</p>
    </div>
  );
});
PrivacyActionRow.displayName = 'PrivacyActionRow';

export { PrivacyActionRow };
