'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconCopy, IconEdit, IconTrash } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import { CATEGORY_MAP, SEVERITY_COLORS, type RiskRule } from './risk-rules-types';

interface RiskRuleRowProps {
  rule: RiskRule;
  /** The name and description the user reads: the locale's for a built-in rule, the stored ones otherwise. */
  name: string;
  description: string | null;
  onToggle: (ruleId: string, enabled: boolean) => void;
  onEdit: (rule: RiskRule) => void;
  onDuplicate: (rule: RiskRule) => void;
  onDelete: (ruleId: string) => void;
}

const SEVERITY_LABEL_KEYS = { low: 'severityLow', medium: 'severityMedium', high: 'severityHigh' } as const;

function RiskRuleRow({ rule, name, description, onToggle, onEdit, onDuplicate, onDelete }: RiskRuleRowProps) {
  const t = useTranslations('settings.securityPolicy.riskRules');
  const severityKey = SEVERITY_LABEL_KEYS[rule.severity as keyof typeof SEVERITY_LABEL_KEYS];

  return (
    <div className="flex items-center gap-3 p-3 border border-border rounded-lg hover:bg-accent/50 transition-colors">
      <Switch
        checked={rule.is_enabled}
        aria-label={name}
        onCheckedChange={(checked) => onToggle(rule.rule_id, checked)}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">{name}</span>
          {rule.is_builtin && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium">
              {t('builtin')}
            </span>
          )}
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${SEVERITY_COLORS[rule.severity] || ''}`}>
            {severityKey ? t(severityKey) : rule.severity}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {t(CATEGORY_MAP[rule.category] || 'categoryCustom')}
          </span>
        </div>
        {description && <p className="text-xs text-muted-foreground mt-0.5 truncate">{description}</p>}
      </div>
      <div className="flex items-center gap-1 flex-shrink-0">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          title={t('editRule')}
          aria-label={t('editRule')}
          onClick={() => onEdit(rule)}
        >
          <IconEdit className="w-3.5 h-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          title={t('duplicateRule')}
          aria-label={t('duplicateRule')}
          onClick={() => onDuplicate(rule)}
        >
          <IconCopy className="w-3.5 h-3.5" />
        </Button>
        {!rule.is_builtin && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-destructive"
            title={t('deleteRule')}
            aria-label={t('deleteRule')}
            onClick={() => onDelete(rule.rule_id)}
          >
            <IconTrash className="w-3.5 h-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

export default memo(RiskRuleRow);
